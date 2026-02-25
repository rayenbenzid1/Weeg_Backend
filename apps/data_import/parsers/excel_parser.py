"""
apps/data_import/parsers/excel_parser.py

Core Excel parsing engine for the WEEG platform.

Handles 5 file types:
    1. branches   — فروع_بروتكتا.xlsx
    2. customers  — العملاء.xlsx
    3. movements  — حركة__المادة_2025.xlsx
    4. inventory  — جرد_افقي_نهاية_السنة_2025.xlsx
    5. aging      — اعمار__الذمم_2025.xlsx

Auto-detection is done by scanning the first row headers.
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from django.db import transaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Detection fingerprints (Arabic header keywords → file type)
# ─────────────────────────────────────────────────────────────────────────────

HEADER_FINGERPRINTS = {
    "branches": ["الفرع", "العنوان", "رقم الهاتف"],
    "customers": ["اسم العميل", "رمز الحساب"],
    "movements": ["رمز  المادة", "حركة.1", "كمية  الادخلات"],
    "inventory": ["رمز المادة", "مخزن المزرعة", "إجمالي كمية"],
    "aging": ["الحالي", "1-30 يوم", "31-60 يوم", "أكثر من 330 يوم"],
}

FILENAME_HINTS = {
    "branches": ["فروع", "branch"],
    "customers": ["العملاء", "customer"],
    "movements": ["حركة", "movement"],
    "inventory": ["جرد", "inventory"],
    "aging": ["اعمار", "aging", "ذمم"],
}

# Movement type mapping (Arabic → English enum value)
MOVEMENT_TYPE_MAP = {
    "ف بيع": "sale",
    "ف شراء": "purchase",
    "ف.أول المدة": "opening_balance",
    "مردودات بيع": "sales_return",
    "مردود شراء": "purchase_return",
    "ادخال رئيسي": "main_entry",
    "اخراج رئيسي": "main_exit",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Safely convert any value to Decimal."""
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError):
        return default


def _to_str(value: Any) -> str:
    """Safely convert any value to a clean string."""
    if value is None:
        return ""
    return str(value).strip()


def _to_date(value: Any) -> Optional[date]:
    """Convert Excel datetime, date string, or None to a Python date."""
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
    except ValueError:
        pass
    return None


def _extract_account_code(account_str: str) -> Optional[str]:
    """
    Extract the numeric account code from an account string.
    Example: "1141001 - عملاء قطاعي / نقدي" → "1141001"
    """
    if not account_str:
        return None
    parts = account_str.split("-", 1)
    code = parts[0].strip()
    return code if code.isdigit() else None


def _load_workbook_rows(file_obj) -> Tuple[List[Any], Any]:
    """Load an Excel file and return (header_row, worksheet)."""
    wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    return rows, wb


# ─────────────────────────────────────────────────────────────────────────────
# File type detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_file_type(filename: str, header_row: tuple) -> Optional[str]:
    """
    Auto-detect the Excel file type using filename hints and header content.

    Returns one of: 'branches', 'customers', 'movements', 'inventory', 'aging', or None.
    """
    filename_lower = filename.lower()

    # Try filename-based detection first (faster)
    for file_type, hints in FILENAME_HINTS.items():
        if any(hint in filename_lower or hint in filename for hint in hints):
            return file_type

    # Fall back to header-based detection
    if not header_row:
        return None

    header_cells = [_to_str(h) for h in header_row if h is not None]
    header_joined = " ".join(header_cells)

    for file_type, keywords in HEADER_FINGERPRINTS.items():
        if all(kw in header_joined for kw in keywords):
            return file_type

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Individual parsers
# ─────────────────────────────────────────────────────────────────────────────

class BranchesParser:
    """
    Parses branches Excel file.

    Expected columns (row 1 = header):
        0: branch_name
        1: address
        2: phone
    """

    def parse(self, rows: List, company) -> Dict:
        from apps.branches.models import Branch

        data_rows = [r for r in rows[1:] if r[0] is not None]
        created = 0
        updated = 0
        errors = []

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                try:
                    branch_name = _to_str(row[0])
                    address = _to_str(row[1]) if len(row) > 1 else ""
                    phone = _to_str(row[2]) if len(row) > 2 else ""

                    if not branch_name:
                        continue

                    branch, was_created = Branch.objects.update_or_create(
                        name=branch_name,
                        defaults={
                            "address": address or None,
                            "phone": phone or None,
                            "is_active": True,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[BranchesParser] Row {i} error: {e}")

        return {
            "total": len(data_rows),
            "created": created,
            "updated": updated,
            "errors": errors,
        }


class CustomersParser:
    """
    Parses customers Excel file (العملاء.xlsx).

    Expected columns:
        0: customer_name
        1: account_code
        2: address
        3: area_code
        4: phone
        5: email
    """

    def parse(self, rows: List, company) -> Dict:
        from apps.customers.models import Customer

        data_rows = [r for r in rows[1:] if r[0] is not None]
        created = 0
        updated = 0
        errors = []

        with transaction.atomic():
            # Wipe existing customers for this company before re-import
            # (full replace strategy — Excel is the source of truth)
            Customer.objects.filter(company=company).delete()

            for i, row in enumerate(data_rows, start=2):
                try:
                    customer_name = _to_str(row[0])
                    account_code = _to_str(row[1]) if len(row) > 1 else ""
                    address = _to_str(row[2]) if len(row) > 2 else ""
                    area_code = _to_str(row[3]) if len(row) > 3 else ""
                    phone = _to_str(row[4]) if len(row) > 4 else ""
                    email = _to_str(row[5]) if len(row) > 5 else ""

                    if not customer_name:
                        continue
                    if not account_code:
                        account_code = f"AUTO-{i}"

                    Customer.objects.create(
                        company=company,
                        customer_name=customer_name,
                        account_code=account_code,
                        address=address or None,
                        area_code=area_code or None,
                        phone=phone or None,
                        email=email or None,
                    )
                    created += 1

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[CustomersParser] Row {i} error: {e}")

        return {
            "total": len(data_rows),
            "created": created,
            "updated": updated,
            "errors": errors,
        }


class MovementsParser:
    """
    Parses material movements Excel file (حركة__المادة_2025.xlsx).

    Expected columns:
        0:  category (الفهرس)
        1:  material_code (رمز المادة)
        2:  lab_code (رمز المعمل)
        3:  material_name (اسم المادة)
        4:  date (تاريخ)
        5:  movement_type_raw (حركة.1)
        6:  qty_in (كمية الادخلات)
        7:  price_in (سعر الادخلات)
        8:  total_in (اجمالي الادخلات)
        9:  qty_out (كمية الاخراجات)
        10: price_out (سعر الاخراجات)
        11: total_out (اجمالي الاخراجات)
        12: balance_price (سعر الرصيد)
        13: branch_name (الفرع)
        14: customer_name (العميل)
    """

    BATCH_SIZE = 500  # Insert in batches for performance

    def parse(self, rows: List, company) -> Dict:
        from apps.transactions.models import MaterialMovement
        from apps.products.models import Product
        from apps.branches.models import Branch
        from apps.customers.models import Customer

        data_rows = [r for r in rows[1:] if r[1] is not None]

        # Build lookup caches to avoid N+1 queries
        product_cache: Dict[str, Optional[Product]] = {}
        branch_cache: Dict[str, Optional[Branch]] = {}
        customer_cache: Dict[str, Optional[Customer]] = {}

        created = 0
        errors = []
        batch = []

        # Clear existing movements for this company
        with transaction.atomic():
            MaterialMovement.objects.filter(company=company).delete()

        for i, row in enumerate(data_rows, start=2):
            try:
                material_code = _to_str(row[1])
                if not material_code:
                    continue

                movement_date = _to_date(row[4])
                if not movement_date:
                    errors.append({"row": i, "error": f"Invalid date: {row[4]}"})
                    continue

                movement_type_raw = _to_str(row[5]) if len(row) > 5 else ""
                movement_type = MOVEMENT_TYPE_MAP.get(movement_type_raw, "other")

                # Resolve product FK (with cache)
                if material_code not in product_cache:
                    product_cache[material_code] = Product.objects.filter(
                        company=company, product_code=material_code
                    ).first()
                product = product_cache[material_code]

                # Resolve branch FK (with cache)
                branch_name = _to_str(row[13]) if len(row) > 13 else ""
                if branch_name and branch_name not in branch_cache:
                    branch_cache[branch_name] = Branch.objects.filter(
                        name__icontains=branch_name
                    ).first()
                branch = branch_cache.get(branch_name)

                # Resolve customer FK (with cache, match on name)
                customer_name = _to_str(row[14]) if len(row) > 14 else ""
                if customer_name and customer_name not in customer_cache:
                    customer_cache[customer_name] = Customer.objects.filter(
                        company=company,
                        customer_name__icontains=customer_name[:50],
                    ).first()
                customer = customer_cache.get(customer_name)

                batch.append(MaterialMovement(
                    company=company,
                    product=product,
                    category=_to_str(row[0]) or None,
                    material_code=material_code,
                    lab_code=_to_str(row[2]) or None,
                    material_name=_to_str(row[3]),
                    movement_date=movement_date,
                    movement_type=movement_type,
                    movement_type_raw=movement_type_raw or None,
                    qty_in=_to_decimal(row[6]) if len(row) > 6 else None,
                    price_in=_to_decimal(row[7]) if len(row) > 7 else None,
                    total_in=_to_decimal(row[8]) if len(row) > 8 else None,
                    qty_out=_to_decimal(row[9]) if len(row) > 9 else None,
                    price_out=_to_decimal(row[10]) if len(row) > 10 else None,
                    total_out=_to_decimal(row[11]) if len(row) > 11 else None,
                    balance_price=_to_decimal(row[12]) if len(row) > 12 else None,
                    branch_name=branch_name or None,
                    branch=branch,
                    customer_name=customer_name or None,
                    customer=customer,
                ))
                created += 1

                # Flush batch
                if len(batch) >= self.BATCH_SIZE:
                    MaterialMovement.objects.bulk_create(batch, ignore_conflicts=False)
                    batch = []

            except Exception as e:
                errors.append({"row": i, "error": str(e)})
                logger.warning(f"[MovementsParser] Row {i} error: {e}")

        # Final flush
        if batch:
            with transaction.atomic():
                MaterialMovement.objects.bulk_create(batch, ignore_conflicts=False)

        return {
            "total": len(data_rows),
            "created": created,
            "updated": 0,
            "errors": errors,
        }


class InventoryParser:
    """
    Parses horizontal inventory Excel file (جرد_افقي_نهاية_السنة_2025.xlsx).

    Expected columns:
        0:  category (الفهرس)
        1:  product_code (رمز المادة)
        2:  product_name (اسم المادة)
        3:  qty_alkarimia
        4:  qty_benghazi
        5:  qty_mazraa
        6:  value_mazraa
        7:  qty_dahmani
        8:  value_dahmani
        9:  qty_janzour
        10: value_janzour
        11: qty_misrata
        12: value_alkarimia
        13: value_misrata
        14: total_qty
        15: cost_price
        16: total_value
    """

    def parse(self, rows: List, company, snapshot_date: date = None) -> Dict:
        from apps.inventory.models import InventorySnapshot
        from apps.products.models import Product

        if snapshot_date is None:
            snapshot_date = date.today()

        data_rows = [r for r in rows[1:] if r[1] is not None]
        created = 0
        updated = 0
        errors = []

        with transaction.atomic():
            # Delete existing snapshot for this date and company
            InventorySnapshot.objects.filter(
                company=company,
                snapshot_date=snapshot_date
            ).delete()

            for i, row in enumerate(data_rows, start=2):
                try:
                    product_code = _to_str(row[1])
                    product_name = _to_str(row[2])
                    category = _to_str(row[0]) or None

                    if not product_code:
                        continue

                    # Get or create product
                    product, prod_created = Product.objects.update_or_create(
                        company=company,
                        product_code=product_code,
                        defaults={
                            "product_name": product_name,
                            "category": category,
                        },
                    )

                    InventorySnapshot.objects.create(
                        company=company,
                        product=product,
                        snapshot_date=snapshot_date,
                        qty_alkarimia=_to_decimal(row[3]) if len(row) > 3 else Decimal("0"),
                        qty_benghazi=_to_decimal(row[4]) if len(row) > 4 else Decimal("0"),
                        qty_mazraa=_to_decimal(row[5]) if len(row) > 5 else Decimal("0"),
                        value_mazraa=_to_decimal(row[6]) if len(row) > 6 else Decimal("0"),
                        qty_dahmani=_to_decimal(row[7]) if len(row) > 7 else Decimal("0"),
                        value_dahmani=_to_decimal(row[8]) if len(row) > 8 else Decimal("0"),
                        qty_janzour=_to_decimal(row[9]) if len(row) > 9 else Decimal("0"),
                        value_janzour=_to_decimal(row[10]) if len(row) > 10 else Decimal("0"),
                        qty_misrata=_to_decimal(row[11]) if len(row) > 11 else Decimal("0"),
                        value_alkarimia=_to_decimal(row[12]) if len(row) > 12 else Decimal("0"),
                        value_misrata=_to_decimal(row[13]) if len(row) > 13 else Decimal("0"),
                        total_qty=_to_decimal(row[14]) if len(row) > 14 else Decimal("0"),
                        cost_price=_to_decimal(row[15]) if len(row) > 15 else Decimal("0"),
                        total_value=_to_decimal(row[16]) if len(row) > 16 else Decimal("0"),
                    )
                    created += 1

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[InventoryParser] Row {i} error: {e}")

        return {
            "total": len(data_rows),
            "created": created,
            "updated": updated,
            "errors": errors,
        }


class AgingParser:
    """
    Parses aging receivables Excel file (اعمار__الذمم_2025.xlsx).

    Expected columns:
        0:  row_number (#)
        1:  account (الحساب)
        2:  current (الحالي)
        3:  d1_30 (1-30 يوم)
        4:  d31_60 (31-60 يوم)
        5:  d61_90 (61-90 يوم)
        6:  d91_120 (91-120 يوم)
        7:  d121_150 (121-150 يوم)
        8:  d151_180 (151-180 يوم)
        9:  d181_210 (181-210 يوم)
        10: d211_240 (211-240 يوم)
        11: d241_270 (241-270 يوم)
        12: d271_300 (271-300 يوم)
        13: d301_330 (301-330 يوم)
        14: over_330 (أكثر من 330 يوم)
        15: total (المجموع) — may be an Excel formula string, ignored
    """

    def parse(self, rows: List, company, report_date: date = None) -> Dict:
        from apps.aging.models import AgingReceivable
        from apps.customers.models import Customer

        if report_date is None:
            report_date = date.today()

        data_rows = [r for r in rows[1:] if r[1] is not None]
        created = 0
        errors = []

        # Build customer lookup by account_code for FK resolution
        customer_map = {
            c.account_code: c
            for c in Customer.objects.filter(company=company)
        }

        with transaction.atomic():
            AgingReceivable.objects.filter(
                company=company,
                report_date=report_date,
            ).delete()

            for i, row in enumerate(data_rows, start=2):
                try:
                    account = _to_str(row[1])
                    if not account:
                        continue

                    # Skip summary/total rows
                    if any(kw in account for kw in ["الإجمالي", "المجموع", "Total"]):
                        continue

                    account_code = _extract_account_code(account)
                    customer = customer_map.get(account_code) if account_code else None

                    def safe_decimal(idx):
                        val = row[idx] if len(row) > idx else None
                        # Skip formula strings
                        if isinstance(val, str) and val.startswith("="):
                            return Decimal("0")
                        return _to_decimal(val)

                    current = safe_decimal(2)
                    d1_30 = safe_decimal(3)
                    d31_60 = safe_decimal(4)
                    d61_90 = safe_decimal(5)
                    d91_120 = safe_decimal(6)
                    d121_150 = safe_decimal(7)
                    d151_180 = safe_decimal(8)
                    d181_210 = safe_decimal(9)
                    d211_240 = safe_decimal(10)
                    d241_270 = safe_decimal(11)
                    d271_300 = safe_decimal(12)
                    d301_330 = safe_decimal(13)
                    over_330 = safe_decimal(14)

                    total = (
                        current + d1_30 + d31_60 + d61_90 + d91_120 +
                        d121_150 + d151_180 + d181_210 + d211_240 +
                        d241_270 + d271_300 + d301_330 + over_330
                    )

                    AgingReceivable.objects.create(
                        company=company,
                        customer=customer,
                        account=account,
                        account_code=account_code,
                        report_date=report_date,
                        current=current,
                        d1_30=d1_30,
                        d31_60=d31_60,
                        d61_90=d61_90,
                        d91_120=d91_120,
                        d121_150=d121_150,
                        d151_180=d151_180,
                        d181_210=d181_210,
                        d211_240=d211_240,
                        d241_270=d241_270,
                        d271_300=d271_300,
                        d301_330=d301_330,
                        over_330=over_330,
                        total=total,
                    )
                    created += 1

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[AgingParser] Row {i} error: {e}")

        return {
            "total": len(data_rows),
            "created": created,
            "updated": 0,
            "errors": errors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Registry & dispatcher
# ─────────────────────────────────────────────────────────────────────────────

PARSERS = {
    "branches": BranchesParser,
    "customers": CustomersParser,
    "movements": MovementsParser,
    "inventory": InventoryParser,
    "aging": AgingParser,
}


def get_parser(file_type: str):
    """Return the parser class for a given file type."""
    parser_class = PARSERS.get(file_type)
    if not parser_class:
        raise ValueError(f"No parser registered for file type: '{file_type}'")
    return parser_class()


def parse_excel_file(
    file_obj,
    filename: str,
    company,
    file_type: str = None,
    extra_context: Dict = None,
) -> Dict:
    """
    Main entry point: parse an Excel file and persist data to the database.

    Args:
        file_obj      : file-like object (Django InMemoryUploadedFile)
        filename      : original filename (used for type detection)
        company       : Company instance
        file_type     : optional override; auto-detected if None
        extra_context : extra parameters passed to the parser
                        (e.g. snapshot_date, report_date)

    Returns:
        dict with keys: file_type, total, created, updated, errors
    """
    extra_context = extra_context or {}

    # Load workbook
    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as e:
        raise ValueError(f"Cannot read Excel file '{filename}': {e}")

    if not rows:
        raise ValueError("The uploaded file is empty.")

    header_row = rows[0]

    # Auto-detect file type
    if not file_type:
        file_type = detect_file_type(filename, header_row)
        if not file_type:
            raise ValueError(
                f"Cannot determine file type for '{filename}'. "
                "Please rename the file to include one of the expected keywords "
                "(فروع, العملاء, حركة, جرد, اعمار) or specify the type manually."
            )

    logger.info(
        f"[parse_excel_file] Parsing '{filename}' as '{file_type}' "
        f"for company '{company.name}' — {len(rows) - 1} data rows."
    )

    parser = get_parser(file_type)

    # Call parser with context-appropriate signature
    if file_type == "inventory":
        result = parser.parse(rows, company, snapshot_date=extra_context.get("snapshot_date"))
    elif file_type == "aging":
        result = parser.parse(rows, company, report_date=extra_context.get("report_date"))
    else:
        result = parser.parse(rows, company)

    result["file_type"] = file_type
    return result
