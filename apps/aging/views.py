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

# Ordered bucket definitions: (field_name, display_label)
AGING_BUCKETS = [
    ("current",   "Current"),
    ("d1_30",     "1–30 days"),
    ("d31_60",    "31–60 days"),
    ("d61_90",    "61–90 days"),
    ("d91_120",   "91–120 days"),
    ("d121_150",  "121–150 days"),
    ("d151_180",  "151–180 days"),
    ("d181_210",  "181–210 days"),
    ("d211_240",  "211–240 days"),
    ("d241_270",  "241–270 days"),
    ("d271_300",  "271–300 days"),
    ("d301_330",  "301–330 days"),
    ("over_330",  "> 330 days"),
]


class AgingListView(APIView):
    """
    GET /api/aging/
    Returns a paginated list of aging receivables.

    Query params:
        report_date=YYYY-MM-DD   — defaults to most recent
        search=<str>             — account or account_code
        risk=low|medium|high|critical  — filter by risk score
        ordering=total | account_code | report_date
        page=<int>   page_size=<int>   — default 50, max 200
    """

    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "total", "-total",
        "account_code", "-account_code",
        "account", "-account",
        "report_date", "-report_date",
    }

    def get(self, request):
        qs = AgingReceivable.objects.filter(
            company=request.user.company
        ).select_related("customer")

        # Default to most recent report date
        report_date = request.query_params.get("report_date")
        if report_date:
            qs = qs.filter(report_date=report_date)
        else:
            latest = (
                AgingReceivable.objects
                .filter(company=request.user.company)
                .order_by("-report_date")
                .values_list("report_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(report_date=latest)
                report_date = str(latest)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(account__icontains=search) |
                Q(account_code__icontains=search)
            )

        # Risk filter: applied in Python (no DB column for risk_score)
        risk_filter = request.query_params.get("risk", "").strip().lower()

        ordering = request.query_params.get("ordering", "-total")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        totals = qs.aggregate(grand_total=Sum("total"))

        # Fetch all for risk filtering (risk is computed in Python)
        all_records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            all_records = [r for r in all_records if r.risk_score == risk_filter]

        total_count = len(all_records)
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start = (page - 1) * page_size
        page_records = all_records[start: start + page_size]

        return Response({
            "report_date": report_date,
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "grand_total": float(totals["grand_total"] or 0),
            "records": AgingListSerializer(page_records, many=True).data,
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
            return Response({"error": "Aging record not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AgingReceivableSerializer(record).data)


class AgingRiskView(APIView):
    """
    GET /api/aging/risk/
    Returns top customers sorted by overdue balance and risk classification.
    Used for the collections risk dashboard widget.

    Query params:
        report_date=YYYY-MM-DD   — defaults to most recent
        risk=high|critical       — filter by risk level (default: all)
        limit=<int>              — number of records to return (default: 20)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AgingReceivable.objects.filter(
            company=request.user.company
        ).select_related("customer").order_by("-total")

        report_date = request.query_params.get("report_date")
        if report_date:
            qs = qs.filter(report_date=report_date)
        else:
            latest = (
                AgingReceivable.objects
                .filter(company=request.user.company)
                .order_by("-report_date")
                .values_list("report_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(report_date=latest)
                report_date = str(latest)

        risk_filter = request.query_params.get("risk", "").strip().lower()
        limit = min(100, max(1, int(request.query_params.get("limit", 20))))

        records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            records = [r for r in records if r.risk_score == risk_filter]
        else:
            # Default: only medium, high, critical
            records = [r for r in records if r.risk_score != "low"]

        records = records[:limit]

        return Response({
            "report_date": report_date,
            "count": len(records),
            "top_risk": [
                {
                    "id": str(r.id),
                    "account": r.account,
                    "account_code": r.account_code,
                    "customer_name": r.customer.customer_name if r.customer else None,
                    "total": float(r.total),
                    "overdue_total": float(r.overdue_total),
                    "risk_score": r.risk_score,
                }
                for r in records
            ],
        })


class AgingDistributionView(APIView):
    """
    GET /api/aging/distribution/
    Returns the sum of each aging bucket across all customers.
    Used to power the aging waterfall/bar chart on the dashboard.

    Query params:
        report_date=YYYY-MM-DD   — defaults to most recent
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AgingReceivable.objects.filter(company=request.user.company)

        report_date = request.query_params.get("report_date")
        if report_date:
            qs = qs.filter(report_date=report_date)
        else:
            latest = (
                AgingReceivable.objects
                .filter(company=request.user.company)
                .order_by("-report_date")
                .values_list("report_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(report_date=latest)
                report_date = str(latest)

        agg_fields = {field: Sum(field) for field, _ in AGING_BUCKETS}
        totals = qs.aggregate(**agg_fields)

        grand_total = sum(float(totals[f] or 0) for f, _ in AGING_BUCKETS)

        distribution = [
            {
                "bucket": field,
                "label": label,
                "total": float(totals[field] or 0),
                "percentage": round(
                    float(totals[field] or 0) / grand_total * 100, 2
                ) if grand_total else 0,
            }
            for field, label in AGING_BUCKETS
        ]

        return Response({
            "report_date": report_date,
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
