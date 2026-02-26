"""
apps/data_import/parsers/excel_parser.py

Core Excel parsing engine for the WEEG platform.

Handles 5 file types:
    1. branches   — فروع_بروتكتا.xlsx
    2. customers  — العملاء.xlsx
    3. movements  — حركة__المادة_2025.xlsx
    4. inventory  — جرد_افقي_نهاية_السنة_2025.xlsx
    5. aging      — اعمار__الذمم_2025.xlsx

Update strategy per file type:
    - branches  : update_or_create on (name)                    — idempotent
    - customers : update_or_create on (company, account_code)   — no destructive DELETE
                  absent accounts → soft-deactivated (is_active=False)
    - movements : date-range delete then bulk_create             — preserves history outside range
    - inventory : update_or_create on (company, product, snapshot_date)
                  stale products for that date → deleted
    - aging     : update_or_create on (company, account_code, report_date)
                  stale accounts for that date → deleted (they've been paid/cleared)
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set

import openpyxl
from django.db import transaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Detection fingerprints
# ─────────────────────────────────────────────────────────────────────────────

HEADER_FINGERPRINTS = {
    "branches":  ["الفرع", "العنوان", "رقم الهاتف"],
    "customers": ["اسم العميل", "رمز الحساب"],
    "movements": ["رمز  المادة", "حركة.1", "كمية  الادخلات"],
    "inventory": ["رمز المادة", "مخزن المزرعة", "إجمالي كمية"],
    "aging":     ["الحالي", "1-30 يوم", "31-60 يوم", "أكثر من 330 يوم"],
}

FILENAME_HINTS = {
    "branches":  ["فروع", "branch"],
    "customers": ["العملاء", "customer"],
    "movements": ["حركة", "movement"],
    "inventory": ["جرد", "inventory"],
    "aging":     ["اعمار", "aging", "ذمم"],
}

MOVEMENT_TYPE_MAP = {
    "ف بيع":        "sale",
    "ف شراء":       "purchase",
    "ف.أول المدة":  "opening_balance",
    "مردودات بيع":  "sales_return",
    "مردود شراء":   "purchase_return",
    "ادخال رئيسي":  "main_entry",
    "اخراج رئيسي":  "main_exit",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError):
        return default


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_account_code(account_str: str) -> Optional[str]:
    """
    Extract numeric code from e.g. "1141001 - عملاء قطاعي / نقدي" → "1141001"
    """
    if not account_str:
        return None
    parts = account_str.split("-", 1)
    code = parts[0].strip()
    return code if code.isdigit() else None


# ─────────────────────────────────────────────────────────────────────────────
# File type detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_file_type(filename: str, header_row: tuple) -> Optional[str]:
    filename_lower = filename.lower()
    for file_type, hints in FILENAME_HINTS.items():
        if any(hint in filename_lower or hint in filename for hint in hints):
            return file_type

    if not header_row:
        return None

    header_joined = " ".join(_to_str(h) for h in header_row if h is not None)
    for file_type, keywords in HEADER_FINGERPRINTS.items():
        if all(kw in header_joined for kw in keywords):
            return file_type

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

class BranchesParser:
    """
    Strategy: update_or_create on (name).
    Never deletes branches — they may have FK relations.
    """

    def parse(self, rows: List, company) -> Dict:
        from apps.branches.models import Branch

        data_rows = [r for r in rows[1:] if r[0] is not None]
        created = updated = 0
        errors = []

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                try:
                    branch_name = _to_str(row[0])
                    if not branch_name:
                        continue
                    _, was_created = Branch.objects.update_or_create(
                        name=branch_name,
                        defaults={
                            "address": _to_str(row[1]) if len(row) > 1 else None or None,
                            "phone":   _to_str(row[2]) if len(row) > 2 else None or None,
                            "is_active": True,
                        },
                    )
                    created += was_created
                    updated += not was_created
                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[BranchesParser] Row {i}: {e}")

        return {"total": len(data_rows), "created": created, "updated": updated, "errors": errors}


class CustomersParser:
    """
    Strategy: update_or_create on (company, account_code).

    - Existing customers → fields updated, is_active reset to True.
    - New account_codes → created.
    - Account codes present in DB but ABSENT from file → is_active=False
      (soft-delete to preserve FK integrity with movements/aging).

    Columns: customer_name | account_code | address | area_code | phone | email
    """

    def parse(self, rows: List, company) -> Dict:
        from apps.customers.models import Customer

        data_rows = [r for r in rows[1:] if r[0] is not None]
        created = updated = 0
        errors = []
        seen_codes: Set[str] = set()

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                try:
                    customer_name = _to_str(row[0])
                    account_code  = _to_str(row[1]) if len(row) > 1 else ""
                    address       = _to_str(row[2]) if len(row) > 2 else ""
                    area_code     = _to_str(row[3]) if len(row) > 3 else ""
                    phone         = _to_str(row[4]) if len(row) > 4 else ""
                    email         = _to_str(row[5]) if len(row) > 5 else ""

                    if not customer_name:
                        continue
                    if not account_code:
                        account_code = f"AUTO-{i}"

                    _, was_created = Customer.objects.update_or_create(
                        company=company,
                        account_code=account_code,
                        defaults={
                            "name": customer_name,
                            "address":   address   or None,
                            "area_code": area_code or None,
                            "phone":     phone     or None,
                            "email":     email     or None,
                            "is_active": True,
                        },
                    )
                    seen_codes.add(account_code)
                    created += was_created
                    updated += not was_created

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[CustomersParser] Row {i}: {e}")

            # Soft-deactivate customers no longer in the file
            deactivated = 0
            if seen_codes:
                deactivated = Customer.objects.filter(
                    company=company,
                    is_active=True,
                ).exclude(account_code__in=seen_codes).update(is_active=False)
                if deactivated:
                    logger.info(
                        f"[CustomersParser] Soft-deactivated {deactivated} customers "
                        "absent from import file."
                    )

        return {
            "total": len(data_rows),
            "created": created,
            "updated": updated,
            "deactivated": deactivated,
            "errors": errors,
        }


class MovementsParser:
    """
    Strategy: date-range delete then bulk_create.

    Because MaterialMovement has no natural unique key (multiple movements of the
    same type can occur on the same day for the same product), we cannot use
    update_or_create. Instead:

        1. Scan all rows to determine [min_date, max_date] covered by the file.
        2. Delete existing movements for this company ONLY within that date range.
        3. Bulk-insert all new rows.

    This means:
        - "Jan–Jun 2025" file  → replaces Jan–Jun only, history before/after preserved.
        - "Jan–Dec 2025" file  → replaces the full year.
        - Running the same file twice is idempotent.

    Columns: category | material_code | lab_code | material_name | date |
             movement_type | qty_in | price_in | total_in |
             qty_out | price_out | total_out | balance_price |
             branch_name | customer_name
    """

    BATCH_SIZE = 500

    def parse(self, rows: List, company) -> Dict:
        from apps.transactions.models import MaterialMovement
        from apps.products.models import Product
        from apps.branches.models import Branch
        from apps.customers.models import Customer

        data_rows = [r for r in rows[1:] if r[1] is not None]

        # Pass 1 — collect valid dates to determine range
        file_dates: List[date] = []
        parsed: List[tuple] = []  # (row_number, row, movement_date)

        for i, row in enumerate(data_rows, start=2):
            d = _to_date(row[4]) if len(row) > 4 else None
            parsed.append((i, row, d))
            if d is not None:
                file_dates.append(d)

        if not file_dates:
            return {
                "total": 0, "created": 0, "updated": 0,
                "errors": [{"row": 0, "error": "No valid dates found in file."}],
            }

        date_from = min(file_dates)
        date_to   = max(file_dates)

        # Build FK caches (avoids N+1 on every row)
        product_cache:  Dict[str, Optional[Product]]  = {}
        branch_cache:   Dict[str, Optional[Branch]]   = {}
        customer_cache: Dict[str, Optional[Customer]] = {}

        created = 0
        errors  = []
        batch:  List[MaterialMovement] = []

        with transaction.atomic():
            # Replace only the date range present in the file
            deleted_count, _ = MaterialMovement.objects.filter(
                company=company,
                movement_date__gte=date_from,
                movement_date__lte=date_to,
            ).delete()
            logger.info(
                f"[MovementsParser] Deleted {deleted_count} movements in range "
                f"{date_from} → {date_to} for company '{company.name}'."
            )

            # Pass 2 — build and insert
            for i, row, movement_date in parsed:
                try:
                    material_code = _to_str(row[1])
                    if not material_code or movement_date is None:
                        if movement_date is None and material_code:
                            errors.append({"row": i, "error": f"Invalid date: {row[4]}"})
                        continue

                    movement_type_raw = _to_str(row[5]) if len(row) > 5 else ""
                    movement_type     = MOVEMENT_TYPE_MAP.get(movement_type_raw, "other")

                    if material_code not in product_cache:
                        product_cache[material_code] = Product.objects.filter(
                            company=company, product_code=material_code
                        ).first()

                    branch_name = _to_str(row[13]) if len(row) > 13 else ""
                    if branch_name and branch_name not in branch_cache:
                        branch_cache[branch_name] = Branch.objects.filter(
                            name__icontains=branch_name
                        ).first()

                    customer_name = _to_str(row[14]) if len(row) > 14 else ""
                    if customer_name and customer_name not in customer_cache:
                        customer_cache[customer_name] = Customer.objects.filter(
                            company=company,
                            name__icontains=customer_name[:50],
                        ).first()

                    batch.append(MaterialMovement(
                        company=company,
                        product=product_cache.get(material_code),
                        category=_to_str(row[0]) or None,
                        material_code=material_code,
                        lab_code=_to_str(row[2]) or None,
                        material_name=_to_str(row[3]),
                        movement_date=movement_date,
                        movement_type=movement_type,
                        movement_type_raw=movement_type_raw or None,
                        qty_in=_to_decimal(row[6])  if len(row) > 6  else None,
                        price_in=_to_decimal(row[7]) if len(row) > 7  else None,
                        total_in=_to_decimal(row[8]) if len(row) > 8  else None,
                        qty_out=_to_decimal(row[9])  if len(row) > 9  else None,
                        price_out=_to_decimal(row[10]) if len(row) > 10 else None,
                        total_out=_to_decimal(row[11]) if len(row) > 11 else None,
                        balance_price=_to_decimal(row[12]) if len(row) > 12 else None,
                        branch_name=branch_name or None,
                        branch=branch_cache.get(branch_name),
                        customer_name=customer_name or None,
                        customer=customer_cache.get(customer_name),
                    ))
                    created += 1

                    if len(batch) >= self.BATCH_SIZE:
                        MaterialMovement.objects.bulk_create(batch)
                        batch = []

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[MovementsParser] Row {i}: {e}")

            if batch:
                MaterialMovement.objects.bulk_create(batch)

        return {
            "total":    len(data_rows),
            "created":  created,
            "updated":  0,
            "date_range":       {"from": str(date_from), "to": str(date_to)},
            "deleted_existing": deleted_count,
            "errors":   errors,
        }


class InventoryParser:
    """
    Strategy: update_or_create on (company, product, snapshot_date).

    - Each product row in the file is upserted for the given snapshot_date.
    - Products that existed in the DB for this snapshot_date but are ABSENT
      from the new file are deleted (e.g. discontinued SKUs).
    - Other snapshot_dates are untouched.

    Columns: category | product_code | product_name |
             qty_alkarimia | qty_benghazi | qty_mazraa | value_mazraa |
             qty_dahmani | value_dahmani | qty_janzour | value_janzour |
             qty_misrata | value_alkarimia | value_misrata |
             total_qty | cost_price | total_value
    """

    def parse(self, rows: List, company, snapshot_date: date = None) -> Dict:
        from apps.inventory.models import InventorySnapshot
        from apps.products.models import Product

        if snapshot_date is None:
            snapshot_date = date.today()

        data_rows = [r for r in rows[1:] if r[1] is not None]
        created = updated = 0
        errors = []
        seen_product_ids: Set[Any] = set()

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                try:
                    product_code = _to_str(row[1])
                    product_name = _to_str(row[2])
                    category     = _to_str(row[0]) or None

                    if not product_code:
                        continue

                    product, _ = Product.objects.update_or_create(
                        company=company,
                        product_code=product_code,
                        defaults={"product_name": product_name, "category": category},
                    )
                    seen_product_ids.add(product.pk)

                    _, was_created = InventorySnapshot.objects.update_or_create(
                        company=company,
                        product=product,
                        snapshot_date=snapshot_date,
                        defaults={
                            "qty_alkarimia":   _to_decimal(row[3])  if len(row) > 3  else Decimal("0"),
                            "qty_benghazi":    _to_decimal(row[4])  if len(row) > 4  else Decimal("0"),
                            "qty_mazraa":      _to_decimal(row[5])  if len(row) > 5  else Decimal("0"),
                            "value_mazraa":    _to_decimal(row[6])  if len(row) > 6  else Decimal("0"),
                            "qty_dahmani":     _to_decimal(row[7])  if len(row) > 7  else Decimal("0"),
                            "value_dahmani":   _to_decimal(row[8])  if len(row) > 8  else Decimal("0"),
                            "qty_janzour":     _to_decimal(row[9])  if len(row) > 9  else Decimal("0"),
                            "value_janzour":   _to_decimal(row[10]) if len(row) > 10 else Decimal("0"),
                            "qty_misrata":     _to_decimal(row[11]) if len(row) > 11 else Decimal("0"),
                            "value_alkarimia": _to_decimal(row[12]) if len(row) > 12 else Decimal("0"),
                            "value_misrata":   _to_decimal(row[13]) if len(row) > 13 else Decimal("0"),
                            "total_qty":       _to_decimal(row[14]) if len(row) > 14 else Decimal("0"),
                            "cost_price":      _to_decimal(row[15]) if len(row) > 15 else Decimal("0"),
                            "total_value":     _to_decimal(row[16]) if len(row) > 16 else Decimal("0"),
                        },
                    )
                    created += was_created
                    updated += not was_created

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[InventoryParser] Row {i}: {e}")

            # Clean up discontinued SKUs for this snapshot date
            if seen_product_ids:
                stale, _ = InventorySnapshot.objects.filter(
                    company=company,
                    snapshot_date=snapshot_date,
                ).exclude(product_id__in=seen_product_ids).delete()
                if stale:
                    logger.info(
                        f"[InventoryParser] Removed {stale} discontinued SKUs "
                        f"from snapshot {snapshot_date}."
                    )

        return {
            "total":         len(data_rows),
            "created":       created,
            "updated":       updated,
            "snapshot_date": str(snapshot_date),
            "errors":        errors,
        }


class AgingParser:
    """
    Strategy: update_or_create on (company, account_code, report_date).

    - Existing records for the same account × date are updated in place.
    - Accounts present in the DB for this report_date but ABSENT from the new
      file are deleted (they've been paid / cleared in the accounting system).
    - Other report_dates are untouched.

    Columns: # | account | current | 1-30d | 31-60d | 61-90d | 91-120d |
             121-150d | 151-180d | 181-210d | 211-240d | 241-270d |
             271-300d | 301-330d | >330d | total (formula, ignored)
    """

    def parse(self, rows: List, company, report_date: date = None) -> Dict:
        from apps.aging.models import AgingReceivable
        from apps.customers.models import Customer

        if report_date is None:
            report_date = date.today()

        data_rows = [r for r in rows[1:] if r[1] is not None]
        created = updated = deleted_stale = 0
        errors = []
        seen_codes: Set[str] = set()

        customer_map = {
            c.account_code: c
            for c in Customer.objects.filter(company=company)
        }

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                try:
                    account = _to_str(row[1])
                    if not account:
                        continue
                    if any(kw in account for kw in ["الإجمالي", "المجموع", "Total"]):
                        continue

                    account_code = _extract_account_code(account) or f"RAW-{account[:30]}"
                    customer     = customer_map.get(account_code)

                    def sd(idx: int) -> Decimal:
                        val = row[idx] if len(row) > idx else None
                        if isinstance(val, str) and val.startswith("="):
                            return Decimal("0")
                        return _to_decimal(val)

                    buckets = {
                        "current":   sd(2),
                        "d1_30":     sd(3),
                        "d31_60":    sd(4),
                        "d61_90":    sd(5),
                        "d91_120":   sd(6),
                        "d121_150":  sd(7),
                        "d151_180":  sd(8),
                        "d181_210":  sd(9),
                        "d211_240":  sd(10),
                        "d241_270":  sd(11),
                        "d271_300":  sd(12),
                        "d301_330":  sd(13),
                        "over_330":  sd(14),
                    }
                    total = sum(buckets.values())

                    _, was_created = AgingReceivable.objects.update_or_create(
                        company=company,
                        account_code=account_code,
                        report_date=report_date,
                        defaults={"customer": customer, "account": account, "total": total, **buckets},
                    )
                    seen_codes.add(account_code)
                    created += was_created
                    updated += not was_created

                except Exception as e:
                    errors.append({"row": i, "error": str(e)})
                    logger.warning(f"[AgingParser] Row {i}: {e}")

            # Remove accounts that were paid/cleared (absent from new report)
            if seen_codes:
                result = AgingReceivable.objects.filter(
                    company=company,
                    report_date=report_date,
                ).exclude(account_code__in=seen_codes).delete()
                deleted_stale = result[0]
                if deleted_stale:
                    logger.info(
                        f"[AgingParser] Removed {deleted_stale} cleared accounts "
                        f"from report {report_date}."
                    )

        return {
            "total":          len(data_rows),
            "created":        created,
            "updated":        updated,
            "deleted_stale":  deleted_stale,
            "report_date":    str(report_date),
            "errors":         errors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Registry & dispatcher
# ─────────────────────────────────────────────────────────────────────────────

PARSERS = {
    "branches":  BranchesParser,
    "customers": CustomersParser,
    "movements": MovementsParser,
    "inventory": InventoryParser,
    "aging":     AgingParser,
}


def get_parser(file_type: str):
    cls = PARSERS.get(file_type)
    if not cls:
        raise ValueError(f"No parser registered for file type: '{file_type}'")
    return cls()


def parse_excel_file(
    file_obj,
    filename: str,
    company,
    file_type: str = None,
    extra_context: Dict = None,
) -> Dict:
    """
    Main entry point: parse an Excel file and persist data to the database.

    Returns a dict with: file_type, total, created, updated, errors, ...
    """
    extra_context = extra_context or {}

    try:
        wb   = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        ws   = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as e:
        raise ValueError(f"Cannot read Excel file '{filename}': {e}")

    if not rows:
        raise ValueError("The uploaded file is empty.")

    if not file_type:
        file_type = detect_file_type(filename, rows[0])
        if not file_type:
            raise ValueError(
                f"Cannot determine file type for '{filename}'. "
                "Rename the file to include one of: فروع, العملاء, حركة, جرد, اعمار — "
                "or pass file_type explicitly."
            )

    logger.info(
        f"[parse_excel_file] '{filename}' → type='{file_type}' "
        f"for '{company.name}' — {len(rows) - 1} data rows."
    )

    parser = get_parser(file_type)

    if file_type == "inventory":
        result = parser.parse(rows, company, snapshot_date=extra_context.get("snapshot_date"))
    elif file_type == "aging":
        result = parser.parse(rows, company, report_date=extra_context.get("report_date"))
    else:
        result = parser.parse(rows, company)

    result["file_type"] = file_type
    return result
