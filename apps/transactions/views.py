from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncMonth
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MaterialMovement
from .serializers import (
    MovementListSerializer,
    MovementDetailSerializer,
)

CALENDAR_MONTHS = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Arabic movement type groups for aggregation (used by summary & KPI views)
SALE_TYPES     = ["ف بيع"]
PURCHASE_TYPES = ["ف شراء"]
RETURN_SALE_TYPES     = ["مردودات بيع"]
RETURN_PURCHASE_TYPES = ["مردود شراء"]


class TransactionListView(APIView):
    """
    GET /api/transactions/

    Query params:
        movement_type=<arabic_value>   — exact match on raw Arabic label
        branch=<str>                   — branch_name icontains
        search=<str>                   — material_code / material_name / customer_name
        date_from=YYYY-MM-DD
        date_to=YYYY-MM-DD
        ordering=<field>
        page=<int>   page_size=<int>   — default 50, max 200
    """

    permission_classes = [IsAuthenticated]
    ALLOWED_ORDERINGS = {
        "movement_date", "-movement_date",
        "material_code", "-material_code",
        "total_in", "-total_in",
        "total_out", "-total_out",
        "created_at", "-created_at",
    }

    def get(self, request):
        qs = MaterialMovement.objects.filter(
            company=request.user.company
        ).select_related("product", "branch", "customer")

        movement_type = request.query_params.get("movement_type", "").strip()
        if movement_type:
            qs = qs.filter(movement_type=movement_type)

        branch = request.query_params.get("branch", "").strip()
        if branch:
            qs = qs.filter(branch_name__icontains=branch)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(material_code__icontains=search) |
                Q(material_name__icontains=search) |
                Q(customer_name__icontains=search) |
                Q(lab_code__icontains=search)
            )

        date_from = request.query_params.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)

        date_to = request.query_params.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)

        ordering = request.query_params.get("ordering", "-movement_date")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        totals = qs.aggregate(
            total_in_value=Sum("total_in"),
            total_out_value=Sum("total_out"),
        )

        total_count = qs.count()
        page      = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start     = (page - 1) * page_size
        qs_page   = qs[start: start + page_size]

        return Response({
            "count":      total_count,
            "page":       page,
            "page_size":  page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "totals": {
                "total_in_value":  float(totals["total_in_value"] or 0),
                "total_out_value": float(totals["total_out_value"] or 0),
            },
            "movements": MovementListSerializer(qs_page, many=True).data,
        })


class TransactionDetailView(APIView):
    """GET /api/transactions/{id}/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, movement_id):
        try:
            movement = MaterialMovement.objects.select_related(
                "product", "branch", "customer"
            ).get(id=movement_id, company=request.user.company)
        except MaterialMovement.DoesNotExist:
            return Response({"error": "Movement not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(MovementDetailSerializer(movement).data)


class TransactionMovementTypesView(APIView):
    """
    GET /api/transactions/movement-types/

    Returns the distinct list of movement_type values present in the DB
    for this company. Used to populate filter dropdowns in the frontend.

    Response: { "movement_types": ["ف بيع", "ف شراء", ...] }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        types = (
            MaterialMovement.objects
            .filter(company=request.user.company)
            .exclude(movement_type="")
            .values_list("movement_type", flat=True)
            .distinct()
            .order_by("movement_type")
        )
        return Response({"movement_types": list(types)})


class TransactionBranchesView(APIView):
    """
    GET /api/transactions/branches/

    Returns the distinct list of branch names present in the DB
    for this company. Used to populate filter dropdowns in the frontend.

    Response: { "branches": ["Branch A", "Branch B", ...] }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        branches = (
            MaterialMovement.objects
            .filter(company=request.user.company)
            .exclude(branch_name__isnull=True)
            .exclude(branch_name="")
            .values_list("branch_name", flat=True)
            .distinct()
            .order_by("branch_name")
        )
        return Response({"branches": list(branches)})


class TransactionSummaryView(APIView):
    """
    GET /api/transactions/summary/
    Monthly aggregated sales vs purchases.

    Query params:
        year=<int>
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MaterialMovement.objects.filter(company=request.user.company)

        year = request.query_params.get("year")
        if year:
            try:
                qs = qs.filter(movement_date__year=int(year))
            except ValueError:
                pass

        monthly = (
            qs.annotate(month=TruncMonth("movement_date"))
            .values("month", "movement_type")
            .annotate(
                total_value=Sum("total_out"),
                row_count=Count("id"),
            )
            .order_by("month")
        )

        pivot = {}
        for row in monthly:
            key = row["month"].strftime("%Y-%m")
            if key not in pivot:
                pivot[key] = {
                    "year":             row["month"].year,
                    "month":            row["month"].month,
                    "month_label":      CALENDAR_MONTHS[row["month"].month],
                    "total_sales":      0,
                    "total_purchases":  0,
                    "sales_count":      0,
                    "purchases_count":  0,
                }
            mt = row["movement_type"]
            if mt in SALE_TYPES or mt in RETURN_SALE_TYPES:
                pivot[key]["total_sales"]  += float(row["total_value"] or 0)
                pivot[key]["sales_count"]  += row["row_count"]
            elif mt in PURCHASE_TYPES or mt in RETURN_PURCHASE_TYPES:
                pivot[key]["total_purchases"] += float(row["total_value"] or 0)
                pivot[key]["purchases_count"] += row["row_count"]

        return Response({"summary": list(pivot.values())})


class TransactionTypeBreakdownView(APIView):
    """
    GET /api/transactions/type-breakdown/
    Totals grouped by movement_type (raw Arabic label).

    Query params:
        date_from / date_to
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MaterialMovement.objects.filter(company=request.user.company)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)

        breakdown = (
            qs.values("movement_type")
            .annotate(
                count=Count("id"),
                total_in=Sum("total_in"),
                total_out=Sum("total_out"),
            )
            .order_by("-count")
        )

        return Response({
            "breakdown": [
                {
                    "movement_type": row["movement_type"],
                    "count":         row["count"],
                    "total_in":      float(row["total_in"] or 0),
                    "total_out":     float(row["total_out"] or 0),
                }
                for row in breakdown
            ]
        })


class TransactionBranchBreakdownView(APIView):
    """
    GET /api/transactions/branch-breakdown/

    Query params:
        movement_type=<arabic_value>   — default: "ف بيع"
        date_from / date_to
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Default to the Arabic sale label
        movement_type = request.query_params.get("movement_type", "ف بيع")

        qs = MaterialMovement.objects.filter(
            company=request.user.company,
            movement_type=movement_type,
        )

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)

        breakdown = (
            qs.values("branch_name")
            .annotate(count=Count("id"), total_out=Sum("total_out"))
            .order_by("-total_out")
        )

        return Response({
            "movement_type": movement_type,
            "branches": [
                {
                    "branch": row["branch_name"] or "Unknown",
                    "count":  row["count"],
                    "total":  float(row["total_out"] or 0),
                }
                for row in breakdown
            ],
        })