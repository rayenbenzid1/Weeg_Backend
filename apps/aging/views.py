"""
apps/aging/views.py  — PATCHED
================================
Key change: AgingListView now resolves a `branch` field for every record
by joining MaterialMovement (حركة المادة) on customer_name.

Fallback chain (same logic as frontend, but now done server-side):
  1. MaterialMovement join  — customer_name match
  2. Arabic keyword in `account` string
  3. Account-code prefix mapping (1141/42/44 → Karimia, 1145 → Janzour, 1146/47 → Misrata)
  4. None
"""

from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AgingReceivable
from .serializers import (
    AgingReceivableSerializer,
    AgingListSerializer,
)

# ── Bucket definitions ────────────────────────────────────────────
AGING_BUCKETS = [
    ("current",   "Current",      0),
    ("d1_30",     "1-30d",       15),
    ("d31_60",    "31-60d",      45),
    ("d61_90",    "61-90d",      75),
    ("d91_120",   "91-120d",    105),
    ("d121_150",  "121-150d",   135),
    ("d151_180",  "151-180d",   165),
    ("d181_210",  "181-210d",   195),
    ("d211_240",  "211-240d",   225),
    ("d241_270",  "241-270d",   255),
    ("d271_300",  "271-300d",   285),
    ("d301_330",  "301-330d",   315),
    ("over_330",  ">330d",      400),
]

# ── Arabic keyword → branch name mapping ─────────────────────────
BRANCH_KEYWORDS = [
    ("مصراتة",   "مخزن صالة عرض مصراتة"),
    ("جنزور",    "مخزن صالة عرض جنزور"),
    ("الدهماني", "مخزن صالة عرض الدهماني"),
    ("الفلاح",   "مخزن صالة عرض الدهماني"),
    ("الكريمية", "مخزن صالة عرض الكريمية"),
    ("المزرعة",  "مخزن المزرعة"),
    ("بنغازي",   "مخزن بنغازي"),
    ("متكاملة",  "مخزن الأنظمة المتكاملة - الكريمية"),
]

# ── Account-code prefix → branch ─────────────────────────────────
# Based on Excel data analysis (اعمار الذمم 2025 + حركة المادة 2025)
CODE_PREFIX_BRANCHES = [
    # 6-digit prefixes first (most specific)
    ("114500", "مخزن صالة عرض جنزور"),
    ("114510", "مخزن صالة عرض جنزور"),
    ("114511", "مخزن صالة عرض جنزور"),
    ("11450",  "مخزن صالة عرض جنزور"),
    ("11451",  "مخزن صالة عرض جنزور"),
    # Misrata
    ("1146",   "مخزن صالة عرض مصراتة"),
    ("1147",   "مخزن صالة عرض مصراتة"),
    # Karimia (HQ) — 1141, 1142, 1143, 1144
    # Note: 1143 contains some Benghazi (caught by keyword above), rest → Karimia
    ("1141",   "مخزن صالة عرض الكريمية"),
    ("1142",   "مخزن صالة عرض الكريمية"),
    ("1143",   "مخزن صالة عرض الكريمية"),
    ("1144",   "مخزن صالة عرض الكريمية"),
]


def _detect_branch_from_text(text: str) -> str | None:
    """Return Arabic branch name if a keyword is found in text."""
    if not text:
        return None
    for keyword, branch in BRANCH_KEYWORDS:
        if keyword in text:
            return branch
    return None


def _detect_branch_from_code(account_code: str) -> str | None:
    """Return Arabic branch name based on account code prefix."""
    if not account_code:
        return None
    code = account_code.strip()
    # Strip leading zeros / spaces
    for prefix, branch in CODE_PREFIX_BRANCHES:
        if code.startswith(prefix):
            return branch
    return None


def _resolve_branch(record: AgingReceivable, sales_map: dict) -> str | None:
    """
    4-layer branch resolution (server-side mirror of frontend logic):
      1. MaterialMovement join via customer name
      2. Arabic keyword in account string
      3. Arabic keyword in customer_name
      4. Account code prefix
    Returns the raw Arabic branch string (same values as مخزن صالة عرض X)
    so the frontend AR_TO_EN table maps it to English without any changes.
    """
    # Layer 1: sales transaction map
    # Customer model uses .name (not .customer_name)
    cname = record.customer.name if record.customer else None
    if cname and cname in sales_map:
        return sales_map[cname]

    # Also try the name part of the account string
    if record.account:
        parts = record.account.split("-", 1)
        acct_name = parts[1].strip() if len(parts) > 1 else ""
        if acct_name and acct_name in sales_map:
            return sales_map[acct_name]

    # Layer 2: keyword in account string
    branch = _detect_branch_from_text(record.account or "")
    if branch:
        return branch

    # Layer 3: keyword in customer_name
    branch = _detect_branch_from_text(cname or "")
    if branch:
        return branch

    # Layer 4: account code prefix
    branch = _detect_branch_from_code(record.account_code or "")
    if branch:
        return branch

    # Try leading digits of the full account string as a code
    if record.account:
        branch = _detect_branch_from_code(record.account)
        if branch:
            return branch

    return None


def _resolve_report_date(company, param):
    if param:
        return param
    return (
        AgingReceivable.objects
        .filter(company=company)
        .order_by("-report_date")
        .values_list("report_date", flat=True)
        .first()
    )


def _build_sales_map(company) -> dict:
    """
    Build {customer_name → branch_name} from MaterialMovement (ف بيع only).
    This is the most reliable source: حركة المادة has الفرع on every row.
    """
    from apps.transactions.models import MaterialMovement
    qs = (
        MaterialMovement.objects
        .filter(company=company, movement_type="ف بيع")
        .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
        .exclude(Q(branch_name__isnull=True) | Q(branch_name=""))
        .values_list("customer_name", "branch_name")
        .distinct()
    )
    sales_map = {}
    for cname, branch in qs:
        if cname and cname not in sales_map:
            sales_map[cname] = branch
    return sales_map


class AgingListView(APIView):
    """
    GET /api/aging/
    Returns paginated aging receivables WITH resolved branch field.

    Query params:
        report_date=YYYY-MM-DD
        search=<str>
        risk=low|medium|high|critical
        ordering=total|account_code|report_date
        page=<int>  page_size=<int>
    """

    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "total", "-total",
        "account_code", "-account_code",
        "account", "-account",
        "report_date", "-report_date",
    }

    def get(self, request):
        company = request.user.company

        report_date = _resolve_report_date(
            company, request.query_params.get("report_date")
        )

        qs_all = AgingReceivable.objects.filter(
            company=company,
            report_date=report_date,
        )
        total_accounts = qs_all.count()
        credit_customers = qs_all.filter(total__gt=0).count()

        qs = qs_all.filter(total__gt=0).select_related("customer")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(account__icontains=search) |
                Q(account_code__icontains=search)
            )

        risk_filter = request.query_params.get("risk", "").strip().lower()

        ordering = request.query_params.get("ordering", "-total")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        totals = qs.aggregate(grand_total=Sum("total"))

        # ── Build branch map from MaterialMovement ───────────────
        sales_map = _build_sales_map(company)

        # ── Fetch all, resolve branch, apply risk filter ─────────
        all_records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            all_records = [r for r in all_records if r.risk_score == risk_filter]

        # ── Serialize + inject branch ────────────────────────────
        total_count = len(all_records)
        page      = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 200))))
        start     = (page - 1) * page_size
        page_records = all_records[start: start + page_size]

        serialized = AgingListSerializer(page_records, many=True).data

        # Inject branch into each serialized record
        for i, record in enumerate(page_records):
            serialized[i]["branch"] = _resolve_branch(record, sales_map)

        return Response({
            "report_date":      str(report_date) if report_date else None,
            "total_accounts":   total_accounts,
            "count":            total_count,
            "credit_customers": credit_customers,
            "page":             page,
            "page_size":        page_size,
            "total_pages":      max(1, (total_count + page_size - 1) // page_size),
            "grand_total":      float(totals["grand_total"] or 0),
            "records":          serialized,
        })


class AgingDetailView(APIView):
    """GET /api/aging/{id}/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, aging_id):
        try:
            record = AgingReceivable.objects.select_related("customer").get(
                id=aging_id,
                company=request.user.company,
            )
        except AgingReceivable.DoesNotExist:
            return Response(
                {"error": "Aging record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = AgingReceivableSerializer(record).data
        # Inject branch
        sales_map = _build_sales_map(request.user.company)
        data["branch"] = _resolve_branch(record, sales_map)
        return Response(data)


class AgingRiskView(APIView):
    """GET /api/aging/risk/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company
        report_date = _resolve_report_date(
            company, request.query_params.get("report_date")
        )

        qs = AgingReceivable.objects.filter(
            company=company,
            report_date=report_date,
        ).select_related("customer").order_by("-total")

        risk_filter = request.query_params.get("risk", "").strip().lower()
        limit = min(100, max(1, int(request.query_params.get("limit", 20))))

        records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            records = [r for r in records if r.risk_score == risk_filter]
        else:
            records = [r for r in records if r.risk_score != "low"]

        records = records[:limit]
        sales_map = _build_sales_map(company)

        return Response({
            "report_date": str(report_date) if report_date else None,
            "count": len(records),
            "top_risk": [
                {
                    "id":            str(r.id),
                    "account":       r.account,
                    "account_code":  r.account_code,
                    "customer_name": (r.customer.name if r.customer else None) or _extract_name(r.account),
                    "branch":        _resolve_branch(r, sales_map),
                    "total":         float(r.total),
                    "overdue_total": float(r.overdue_total),
                    "risk_score":    r.risk_score,
                }
                for r in records
            ],
        })


class AgingDistributionView(APIView):
    """GET /api/aging/distribution/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company
        report_date = _resolve_report_date(
            company, request.query_params.get("report_date")
        )

        qs = AgingReceivable.objects.filter(
            company=company,
            report_date=report_date,
        )

        agg_fields = {field: Sum(field) for field, _, _ in AGING_BUCKETS}
        totals     = qs.aggregate(**agg_fields)

        grand_total = sum(float(totals[f] or 0) for f, _, _ in AGING_BUCKETS)

        distribution = [
            {
                "bucket":        field,
                "label":         label,
                "total":         float(totals[field] or 0),
                "percentage":    round(
                    float(totals[field] or 0) / grand_total * 100, 2
                ) if grand_total else 0,
                "midpoint_days": midpoint,
            }
            for field, label, midpoint in AGING_BUCKETS
        ]

        return Response({
            "report_date": str(report_date) if report_date else None,
            "grand_total": round(grand_total, 2),
            "distribution": distribution,
        })


class AgingReportDatesView(APIView):
    """GET /api/aging/dates/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        dates = (
            AgingReceivable.objects
            .filter(company=request.user.company)
            .values_list("report_date", flat=True)
            .distinct()
            .order_by("-report_date")
        )
        return Response({"dates": [str(d) for d in dates]})