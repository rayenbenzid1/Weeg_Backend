from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InventorySnapshot
from .serializers import (
    InventorySnapshotSerializer,
    InventorySnapshotListSerializer,
)


class InventoryListView(APIView):
    """
    GET /api/inventory/
    Returns the inventory snapshot list for the company.

    Query params:
        snapshot_date=YYYY-MM-DD   — exact date filter (required or uses latest)
        category=<str>             — filter by product category
        search=<str>               — filter by product name or code
        ordering=product_name | total_qty | total_value | category
        page=<int>   page_size=<int>  — default 50, max 200
    """

    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "product__product_name", "-product__product_name",
        "product__category", "-product__category",
        "total_qty", "-total_qty",
        "total_value", "-total_value",
    }

    def get(self, request):
        qs = InventorySnapshot.objects.filter(
            company=request.user.company
        ).select_related("product")

        # If no date specified, default to the most recent snapshot date
        snapshot_date = request.query_params.get("snapshot_date")
        if snapshot_date:
            qs = qs.filter(snapshot_date=snapshot_date)
        else:
            latest = (
                InventorySnapshot.objects
                .filter(company=request.user.company)
                .order_by("-snapshot_date")
                .values_list("snapshot_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(snapshot_date=latest)
                snapshot_date = str(latest)

        category = request.query_params.get("category", "").strip()
        if category:
            qs = qs.filter(product__category__icontains=category)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(product__product_name__icontains=search) |
                Q(product__product_code__icontains=search)
            )

        ordering = request.query_params.get("ordering", "product__product_name")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        # Summary totals for the filtered set
        totals = qs.aggregate(
            grand_total_qty=Sum("total_qty"),
            grand_total_value=Sum("total_value"),
        )

        total_count = qs.count()
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start = (page - 1) * page_size
        qs_page = qs[start: start + page_size]

        return Response({
            "snapshot_date": snapshot_date,
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "totals": {
                "grand_total_qty": float(totals["grand_total_qty"] or 0),
                "grand_total_value": float(totals["grand_total_value"] or 0),
            },
            "items": InventorySnapshotListSerializer(qs_page, many=True).data,
        })


class InventoryDetailView(APIView):
    """
    GET /api/inventory/{id}/
    Returns full snapshot detail including all branch breakdowns.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, snapshot_id):
        try:
            snapshot = InventorySnapshot.objects.select_related("product").get(
                id=snapshot_id,
                company=request.user.company,
            )
        except InventorySnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InventorySnapshotSerializer(snapshot).data)


class InventoryBranchSummaryView(APIView):
    """
    GET /api/inventory/branch-summary/

    Returns aggregated stock totals per branch for a given snapshot date.
    Used to power the cross-branch comparison chart on the dashboard.

    Query params:
        snapshot_date=YYYY-MM-DD   — defaults to most recent date
        category=<str>             — optional category filter
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = InventorySnapshot.objects.filter(company=request.user.company)

        snapshot_date = request.query_params.get("snapshot_date")
        if snapshot_date:
            qs = qs.filter(snapshot_date=snapshot_date)
        else:
            latest = (
                InventorySnapshot.objects
                .filter(company=request.user.company)
                .order_by("-snapshot_date")
                .values_list("snapshot_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(snapshot_date=latest)
                snapshot_date = str(latest)

        category = request.query_params.get("category", "").strip()
        if category:
            qs = qs.filter(product__category__icontains=category)

        totals = qs.aggregate(
            qty_alkarimia=Sum("qty_alkarimia"),
            qty_benghazi=Sum("qty_benghazi"),
            qty_mazraa=Sum("qty_mazraa"),
            qty_dahmani=Sum("qty_dahmani"),
            qty_janzour=Sum("qty_janzour"),
            qty_misrata=Sum("qty_misrata"),
            value_alkarimia=Sum("value_alkarimia"),
            value_mazraa=Sum("value_mazraa"),
            value_dahmani=Sum("value_dahmani"),
            value_janzour=Sum("value_janzour"),
            value_misrata=Sum("value_misrata"),
        )

        def f(v):
            return float(v or 0)

        branches = [
            {"branch": "Al-Karimia",  "total_qty": f(totals["qty_alkarimia"]),  "total_value": f(totals["value_alkarimia"])},
            {"branch": "Benghazi",    "total_qty": f(totals["qty_benghazi"]),    "total_value": 0},
            {"branch": "Al-Mazraa",   "total_qty": f(totals["qty_mazraa"]),      "total_value": f(totals["value_mazraa"])},
            {"branch": "Dahmani",     "total_qty": f(totals["qty_dahmani"]),     "total_value": f(totals["value_dahmani"])},
            {"branch": "Janzour",     "total_qty": f(totals["qty_janzour"]),     "total_value": f(totals["value_janzour"])},
            {"branch": "Misrata",     "total_qty": f(totals["qty_misrata"]),     "total_value": f(totals["value_misrata"])},
        ]

        return Response({
            "snapshot_date": snapshot_date,
            "branches": branches,
        })


class InventorySnapshotDatesView(APIView):
    """
    GET /api/inventory/dates/
    Returns the list of available snapshot dates (for the date picker in the UI).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        dates = (
            InventorySnapshot.objects
            .filter(company=request.user.company)
            .values_list("snapshot_date", flat=True)
            .distinct()
            .order_by("-snapshot_date")
        )
        return Response({"dates": [str(d) for d in dates]})


class InventoryCategoryBreakdownView(APIView):
    """
    GET /api/inventory/category-breakdown/

    Returns total qty and value grouped by category for a given snapshot date.
    Used for the category distribution chart.

    Query params:
        snapshot_date=YYYY-MM-DD
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = InventorySnapshot.objects.filter(
            company=request.user.company
        ).select_related("product")

        snapshot_date = request.query_params.get("snapshot_date")
        if snapshot_date:
            qs = qs.filter(snapshot_date=snapshot_date)
        else:
            latest = (
                InventorySnapshot.objects
                .filter(company=request.user.company)
                .order_by("-snapshot_date")
                .values_list("snapshot_date", flat=True)
                .first()
            )
            if latest:
                qs = qs.filter(snapshot_date=latest)
                snapshot_date = str(latest)

        breakdown = (
            qs.values("product__category")
            .annotate(
                total_qty=Sum("total_qty"),
                total_value=Sum("total_value"),
            )
            .order_by("-total_value")
        )

        return Response({
            "snapshot_date": snapshot_date,
            "categories": [
                {
                    "category": row["product__category"] or "Uncategorized",
                    "total_qty": float(row["total_qty"] or 0),
                    "total_value": float(row["total_value"] or 0),
                }
                for row in breakdown
            ],
        })
