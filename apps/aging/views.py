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

# Ordered bucket definitions: (field_name, display_label, midpoint_days)
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


def _resolve_report_date(company, param):
    """Return the report_date to use: param if provided, else latest in DB."""
    if param:
        return param
    return (
        AgingReceivable.objects
        .filter(company=company)
        .order_by("-report_date")
        .values_list("report_date", flat=True)
        .first()
    )


class AgingListView(APIView):
    """
    GET /api/aging/
    Returns a paginated list of aging receivables.

    Query params:
        report_date=YYYY-MM-DD        — defaults to most recent
        search=<str>                  — account or account_code
        risk=low|medium|high|critical — filter by risk score
        ordering=total|account_code|report_date
        page=<int>  page_size=<int>   — default 50, max 200

    Response includes:
        total_accounts  — ALL rows in this report (e.g. 377), changes per import
        count           — rows with balance > 0 in this report (e.g. 174)
        records         — paginated list (balance > 0 only)
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

        # Resolve report date first
        report_date = _resolve_report_date(
            company, request.query_params.get("report_date")
        )

        # ── qs_all: ALL rows for this report date, NO balance filter ─────────
        # This represents every line in the imported Excel file.
        qs_all = AgingReceivable.objects.filter(
            company=company,
            report_date=report_date,
        )

        # total_accounts = total rows in the imported Excel for this report
        # e.g. 377 — includes accounts with balance = 0
        # This number changes every time a new Excel is imported.
        total_accounts = qs_all.count()

        # credit_customers = accounts with an open balance > 0 in this report
        # e.g. 174
        credit_customers = qs_all.filter(total__gt=0).count()

        # ── qs: filtered queryset for display (balance > 0 only) ─────────────
        qs = qs_all.filter(total__gt=0).select_related("customer")

        # Search filter
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(account__icontains=search) |
                Q(account_code__icontains=search)
            )

        # Risk filter (computed in Python — no DB column)
        risk_filter = request.query_params.get("risk", "").strip().lower()

        # Ordering
        ordering = request.query_params.get("ordering", "-total")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        # Grand total
        totals = qs.aggregate(grand_total=Sum("total"))

        # Fetch all for risk filtering
        all_records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            all_records = [r for r in all_records if r.risk_score == risk_filter]

        # Pagination
        total_count = len(all_records)
        page      = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start     = (page - 1) * page_size
        page_records = all_records[start: start + page_size]

        return Response({
            "report_date":    str(report_date) if report_date else None,
            "total_accounts": total_accounts,   # 377 — ALL rows in this Excel import
            "count":          total_count,      # 174 — rows with balance > 0
            "credit_customers": credit_customers,
            "page":           page,
            "page_size":      page_size,
            "total_pages":    max(1, (total_count + page_size - 1) // page_size),
            "grand_total":    float(totals["grand_total"] or 0),
            "records":        AgingListSerializer(page_records, many=True).data,
        })


class AgingDetailView(APIView):
    """
    GET /api/aging/{id}/
    Returns the full aging record including all bucket breakdowns.
    """

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
        return Response(AgingReceivableSerializer(record).data)


class AgingRiskView(APIView):
    """
    GET /api/aging/risk/
    Returns top customers sorted by overdue balance and risk classification.

    Query params:
        report_date=YYYY-MM-DD        — defaults to most recent
        risk=high|critical            — filter by risk level (default: all non-low)
        limit=<int>                   — number of records (default: 20)
    """

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

        return Response({
            "report_date": str(report_date) if report_date else None,
            "count": len(records),
            "top_risk": [
                {
                    "id":            str(r.id),
                    "account":       r.account,
                    "account_code":  r.account_code,
                    "customer_name": r.customer.name if r.customer else None,
                    "total":         float(r.total),
                    "overdue_total": float(r.overdue_total),
                    "risk_score":    r.risk_score,
                }
                for r in records
            ],
        })


class AgingDistributionView(APIView):
    """
    GET /api/aging/distribution/
    Returns the sum of each aging bucket across all customers.

    Query params:
        report_date=YYYY-MM-DD — defaults to most recent
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company

        report_date = _resolve_report_date(
            company, request.query_params.get("report_date")
        )

        # Aggregate ALL rows for this report (no total>0 filter)
        # so bucket sums match the Excel exactly (e.g. current = 95,632)
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
                "total":        float(totals[field] or 0),
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
    """
    GET /api/aging/dates/
    Returns available report dates for the date picker in the UI.
    """

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