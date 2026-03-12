from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InventorySnapshot, InventorySnapshotLine
from .serializers import (
    InventorySnapshotSerializer,
    InventorySnapshotListSerializer,
    InventorySnapshotLineSerializer,
)
from apps.branches.resolver import BranchResolver   # ← ajouter cet import en haut du fichier


def _get_company_name(request):
    """
    Returns (company_name: str, error: Response|None).
    If the user has no associated company the behaviour depends on roles:
      * normal users -> 403 error
      * superusers/staff -> may pass `?company_name=` to specify a target
    This makes it possible to inspect inventory for other companies when using
    an admin account (used in development).
    """
    if request.user.company:
        return request.user.company.name, None

    # allow superuser/staff to override via queryparam
    if request.user.is_active and (request.user.is_staff or request.user.is_superuser):
        name = request.query_params.get("company_name", "").strip()
        if name:
            return name, None
        return None, Response(
            {"error": "Please provide company_name query parameter for admin access."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None, Response(
        {"error": "Your account is not linked to a company."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _safe_int(value, default: int, min_val: int, max_val: int) -> int:
    try:
        return max(min_val, min(max_val, int(value)))
    except (TypeError, ValueError):
        return default


class InventoryListView(APIView):
    """
    GET /api/inventory/
    Returns a paginated list of InventorySnapshot sessions for the company.
    Each item contains aggregated line_count and total_lines_value.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_name, err = _get_company_name(request)
        if err:
            return err

        qs = (
            InventorySnapshot.objects
            .filter(company_name=company_name)
            .annotate(
                line_count=Count("lines"),
                total_lines_value=Sum("lines__line_value"),
            )
            .order_by("-uploaded_at")
        )

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(label__icontains=search) | Q(source_file__icontains=search)
            )

        total = qs.count()
        page      = _safe_int(request.query_params.get("page", 1),      default=1,   min_val=1,  max_val=10_000)
        page_size = _safe_int(request.query_params.get("page_size", 20), default=20,  min_val=1,  max_val=100)
        qs_page = qs[(page - 1) * page_size: page * page_size]

        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "items": InventorySnapshotListSerializer(qs_page, many=True).data,
        })


class InventoryDetailView(APIView):
    """
    GET /api/inventory/<uuid:snapshot_id>/
    Returns snapshot metadata + branch list. Lines are in a separate endpoint.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, snapshot_id):
        company_name, err = _get_company_name(request)
        if err:
            return err
        try:
            snapshot = (
                InventorySnapshot.objects
                .annotate(
                    line_count=Count("lines"),
                    total_lines_value=Sum("lines__line_value"),
                )
                .get(id=snapshot_id, company_name=company_name)
            )
        except InventorySnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InventorySnapshotSerializer(snapshot).data)

    def delete(self, request, snapshot_id):
        company_name, err = _get_company_name(request)
        if err:
            return err
        try:
            snapshot = InventorySnapshot.objects.get(
                id=snapshot_id,
                company_name=company_name,
            )
        except InventorySnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)
        snapshot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventorySnapshotLinesView(APIView):
    """
    GET /api/inventory/<uuid:snapshot_id>/lines/
    Returns paginated InventorySnapshotLine rows for one snapshot.
    Supports ?branch=, ?search=, ?page=, ?page_size=
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, snapshot_id):
        company_name, err = _get_company_name(request)
        if err:
            return err
        try:
            snapshot = InventorySnapshot.objects.get(
                id=snapshot_id,
                company_name=company_name,
            )
        except InventorySnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = snapshot.lines.all()

        branch = request.query_params.get("branch", "").strip()
        if branch:
            qs = qs.filter(branch_name__icontains=branch)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(product_name__icontains=search) | Q(product_code__icontains=search)
            )

        totals = qs.aggregate(
            grand_total_qty=Sum("quantity"),
            grand_total_value=Sum("line_value"),
        )
        distinct_products  = qs.values("product_code").distinct().count()
        out_of_stock_count = qs.filter(quantity=0).count()
        critical_count     = qs.filter(quantity__gt=0, quantity__lt=30).count()
        low_count          = qs.filter(quantity__gte=30, quantity__lte=50).count()

        total = qs.count()
        page      = _safe_int(request.query_params.get("page", 1),       default=1,   min_val=1, max_val=10_000)
        page_size = _safe_int(request.query_params.get("page_size", 100), default=100, min_val=1, max_val=500)
        qs_page = qs[(page - 1) * page_size: page * page_size]

        return Response({
            "snapshot_id": str(snapshot_id),
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "totals": {
                "grand_total_qty":    float(totals["grand_total_qty"]   or 0),
                "grand_total_value":  float(totals["grand_total_value"] or 0),
                "distinct_products":  distinct_products,
                "out_of_stock_count": out_of_stock_count,
                "critical_count":     critical_count,
                "low_count":          low_count,
            },
            "lines": InventorySnapshotLineSerializer(qs_page, many=True).data,
        })


class InventoryBranchSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_name, err = _get_company_name(request)
        if err:
            return err

        qs = InventorySnapshotLine.objects.filter(
            snapshot__company_name=company_name,
        )
        snapshot_id = request.query_params.get("snapshot_id", "").strip()
        if snapshot_id:
            qs = qs.filter(snapshot_id=snapshot_id)

        rows = (
            qs.values("branch_name")
            .annotate(
                total_qty=Sum("quantity"),
                total_value=Sum("line_value"),
            )
            .order_by("branch_name")
        )

        # ── Normaliser via BranchResolver ─────────────────────────────────
        company  = request.user.company
        resolver = BranchResolver(company) if company else None

        merged: dict[str, dict] = {}
        for r in rows:
            raw = r["branch_name"] or "Unknown"

            # Résoudre vers le nom canonique
            if resolver:
                branch_obj = resolver.resolve(raw)
                canonical  = branch_obj.name if branch_obj else raw
            else:
                canonical = raw

            qty   = float(r["total_qty"]   or 0)
            value = float(r["total_value"] or 0)

            if canonical in merged:
                merged[canonical]["total_qty"]   += qty
                merged[canonical]["total_value"] += value
            else:
                merged[canonical] = {"total_qty": qty, "total_value": value}

        return Response({
            "branches": [
                {
                    "branch":      name,
                    "total_qty":   data["total_qty"],
                    "total_value": data["total_value"],
                }
                for name, data in sorted(merged.items())
            ],
        })
class InventoryCategoryBreakdownView(APIView):
    """
    GET /api/inventory/category-breakdown/
    Aggregates quantity + value by product_category.
    Optional ?snapshot_id= to scope to a single import session.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_name, err = _get_company_name(request)
        if err:
            return err

        qs = InventorySnapshotLine.objects.filter(
            snapshot__company_name=company_name,
        )
        snapshot_id = request.query_params.get("snapshot_id", "").strip()
        if snapshot_id:
            qs = qs.filter(snapshot_id=snapshot_id)

        breakdown = (
            qs.values("product_category")
            .annotate(
                total_qty=Sum("quantity"),
                total_value=Sum("line_value"),
            )
            .order_by("-total_value")
        )

        return Response({
            "categories": [
                {
                    "category": r["product_category"] or "Uncategorized",
                    "total_qty": float(r["total_qty"] or 0),
                    "total_value": float(r["total_value"] or 0),
                }
                for r in breakdown
            ],
        })


class InventorySnapshotDatesView(APIView):
    """GET /api/inventory/dates/ — distinct import dates."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_name, err = _get_company_name(request)
        if err:
            return err

        dates = (
            InventorySnapshot.objects
            .filter(company_name=company_name)
            .annotate(import_date=TruncDate("uploaded_at"))
            .values_list("import_date", flat=True)
            .distinct()
            .order_by("-import_date")
        )
        return Response({"dates": [str(d) for d in dates if d]})
