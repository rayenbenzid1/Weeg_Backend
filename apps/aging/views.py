from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AgingReceivable, AgingSnapshot
from .serializers import AgingReceivableSerializer, AgingListSerializer, AgingSnapshotSerializer

AGING_BUCKETS = [
    ("current", "Current", 0),
    ("d1_30", "1-30d", 15),
    ("d31_60", "31-60d", 45),
    ("d61_90", "61-90d", 75),
    ("d91_120", "91-120d", 105),
    ("d121_150", "121-150d", 135),
    ("d151_180", "151-180d", 165),
    ("d181_210", "181-210d", 195),
    ("d211_240", "211-240d", 225),
    ("d241_270", "241-270d", 255),
    ("d271_300", "271-300d", 285),
    ("d301_330", "301-330d", 315),
    ("over_330", ">330d", 400),
]


def _build_sales_map(company) -> dict:
    from apps.transactions.models import MaterialMovement

    qs = (
        MaterialMovement.objects
        .filter(company=company, movement_type="ف بيع")
        .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
        .exclude(Q(branch__name__isnull=True) | Q(branch__name=""))
        .values_list("customer_name", "branch__name")
        .distinct()
    )
    sales_map = {}
    for cname, branch_name in qs:
        if cname and cname not in sales_map:
            sales_map[cname] = branch_name
    return sales_map


def _resolve_branch(record: AgingReceivable, sales_map: dict):
    cname = record.customer.name if record.customer else None
    if cname and cname in sales_map:
        return sales_map[cname]
    return None


def _get_snapshot_and_qs(company, snapshot_id_param: str):
    """
    Returns (snapshot, qs).
    - If snapshot_id_param given, fetch that specific snapshot (404 if missing).
    - Otherwise defaults to the latest snapshot for the company.
    Returns (None, None)          → caller should return 404.
    Returns (None, empty_qs)      → company has no snapshots yet (return empty data).
    Returns (snapshot, qs)        → normal path.
    """
    if snapshot_id_param:
        try:
            snapshot = AgingSnapshot.objects.get(id=snapshot_id_param, company=company)
        except AgingSnapshot.DoesNotExist:
            return None, None
    else:
        snapshot = AgingSnapshot.objects.filter(company=company).order_by("-uploaded_at").first()

    if snapshot is None:
        return None, AgingReceivable.objects.none()

    return snapshot, AgingReceivable.objects.filter(snapshot=snapshot)


class AgingSnapshotListView(APIView):
    """
    GET  /api/aging/snapshots/           → list all snapshots (newest first)
    DELETE /api/aging/snapshots/<uuid>/  → delete (roll back) a snapshot
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company
        snapshots = AgingSnapshot.objects.filter(company=company).order_by("-uploaded_at")
        data = AgingSnapshotSerializer(snapshots, many=True).data
        return Response({"count": len(data), "items": data})

    def delete(self, request, snapshot_id):
        company = request.user.company
        try:
            snapshot = AgingSnapshot.objects.get(id=snapshot_id, company=company)
        except AgingSnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)
        snapshot.delete()
        return Response({"deleted": str(snapshot_id)}, status=status.HTTP_200_OK)


class AgingListView(APIView):
    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "total", "-total",
        "account_code", "-account_code",
        "account", "-account",
        "created_at", "-created_at",
    }

    def get(self, request):
        company = request.user.company
        snapshot_id_param = request.query_params.get("snapshot_id", "").strip()

        snapshot, qs_all = _get_snapshot_and_qs(company, snapshot_id_param)
        if snapshot is None and snapshot_id_param:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)

        total_accounts = qs_all.count()
        credit_customers = qs_all.filter(total__gt=0).count()

        qs = qs_all.filter(total__gt=0).select_related("customer")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(account__icontains=search) | Q(account_code__icontains=search))

        risk_filter = request.query_params.get("risk", "").strip().lower()

        ordering = request.query_params.get("ordering", "-total")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        totals = qs.aggregate(grand_total=Sum("total"))

        sales_map = _build_sales_map(company)
        all_records = list(qs)
        if risk_filter in ("low", "medium", "high", "critical"):
            all_records = [r for r in all_records if r.risk_score == risk_filter]

        total_count = len(all_records)
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 200))))
        start = (page - 1) * page_size
        page_records = all_records[start: start + page_size]

        serialized = AgingListSerializer(page_records, many=True).data
        for i, record in enumerate(page_records):
            serialized[i]["branch"] = _resolve_branch(record, sales_map)

        return Response({
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "report_date": str(snapshot.report_date or snapshot.uploaded_at.date()) if snapshot else None,
            "uploaded_at": snapshot.uploaded_at.isoformat() if snapshot else None,
            "total_accounts": total_accounts,
            "count": total_count,
            "credit_customers": credit_customers,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "grand_total": float(totals["grand_total"] or 0),
            "records": serialized,
        })


class AgingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, aging_id):
        try:
            record = AgingReceivable.objects.select_related("customer").get(
                id=aging_id,
                company=request.user.company,
            )
        except AgingReceivable.DoesNotExist:
            return Response({"error": "Aging record not found."}, status=status.HTTP_404_NOT_FOUND)

        data = AgingReceivableSerializer(record).data
        sales_map = _build_sales_map(request.user.company)
        data["branch"] = _resolve_branch(record, sales_map)
        return Response(data)


class AgingRiskView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company
        snapshot_id_param = request.query_params.get("snapshot_id", "").strip()

        snapshot, qs = _get_snapshot_and_qs(company, snapshot_id_param)
        if snapshot is None and snapshot_id_param:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = qs.select_related("customer").order_by("-total")

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
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "count": len(records),
            "top_risk": [
                {
                    "id": str(r.id),
                    "account": r.account,
                    "account_code": r.account_code,
                    "customer_name": (r.customer.name if r.customer else None),
                    "branch": _resolve_branch(r, sales_map),
                    "total": float(r.total),
                    "overdue_total": float(r.overdue_total),
                    "risk_score": r.risk_score,
                }
                for r in records
            ],
        })


class AgingDistributionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company
        snapshot_id_param = request.query_params.get("snapshot_id", "").strip()

        snapshot, qs = _get_snapshot_and_qs(company, snapshot_id_param)
        if snapshot is None and snapshot_id_param:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)

        agg_fields = {field: Sum(field) for field, _, _ in AGING_BUCKETS}
        totals = qs.aggregate(**agg_fields)

        grand_total = sum(float(totals[f] or 0) for f, _, _ in AGING_BUCKETS)

        distribution = [
            {
                "bucket": field,
                "label": label,
                "total": float(totals[field] or 0),
                "percentage": round(float(totals[field] or 0) / grand_total * 100, 2) if grand_total else 0,
                "midpoint_days": midpoint,
            }
            for field, label, midpoint in AGING_BUCKETS
        ]

        return Response({"grand_total": round(grand_total, 2), "distribution": distribution})


class AgingReportDatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snapshots = (
            AgingSnapshot.objects
            .filter(company=request.user.company)
            .order_by("-uploaded_at")
            .values("id", "report_date", "uploaded_at")
        )
        dates = [
            str(s["report_date"] or s["uploaded_at"].date())
            for s in snapshots
        ]
        return Response({"dates": dates})



