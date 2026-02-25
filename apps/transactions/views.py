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


class TransactionListView(APIView):
    """
    GET /api/transactions/
    Returns a paginated, filtered list of material movements.

    Query params:
        movement_type=<sale|purchase|opening_balance|sales_return|
                       purchase_return|main_entry|main_exit|other>
        branch=<str>           — branch_name icontains
        search=<str>           — material_code / material_name / customer_name
        date_from=YYYY-MM-DD
        date_to=YYYY-MM-DD
        ordering=<field>       — movement_date | material_code | total_out | total_in
        page=<int>
        page_size=<int>        — default 50, max 200
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

        # ── Filters ───────────────────────────────────────────────────────────
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

        # ── Ordering ──────────────────────────────────────────────────────────
        ordering = request.query_params.get("ordering", "-movement_date")
        if ordering in self.ALLOWED_ORDERINGS:
            qs = qs.order_by(ordering)

        # ── Aggregated totals for the filtered set ────────────────────────────
        totals = qs.aggregate(
            total_in_value=Sum("total_in"),
            total_out_value=Sum("total_out"),
        )

        # ── Pagination ────────────────────────────────────────────────────────
        total_count = qs.count()
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start = (page - 1) * page_size
        qs_page = qs[start: start + page_size]

        return Response({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "totals": {
                "total_in_value": float(totals["total_in_value"] or 0),
                "total_out_value": float(totals["total_out_value"] or 0),
            },
            "movements": MovementListSerializer(qs_page, many=True).data,
        })


class TransactionDetailView(APIView):
    """
    GET /api/transactions/{id}/
    Returns the full movement record including all FK-resolved fields.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, movement_id):
        try:
            movement = MaterialMovement.objects.select_related(
                "product", "branch", "customer"
            ).get(id=movement_id, company=request.user.company)
        except MaterialMovement.DoesNotExist:
            return Response({"error": "Movement not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(MovementDetailSerializer(movement).data)


class TransactionSummaryView(APIView):
    """
    GET /api/transactions/summary/
    Returns monthly aggregated sales vs purchases.
    Used to power the revenue trend chart on the dashboard.

    Query params:
        year=<int>   — default: current year from DB
        months=<int> — how many months back (default: 12)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MaterialMovement.objects.filter(company=request.user.company)

        # Optional year filter
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
                total_value=Sum("total_out") + Sum("total_in"),
                row_count=Count("id"),
            )
            .order_by("month")
        )

        # Pivot: group by month → {sales, purchases}
        pivot = {}
        for row in monthly:
            key = row["month"].strftime("%Y-%m")
            if key not in pivot:
                pivot[key] = {
                    "year": row["month"].year,
                    "month": row["month"].month,
                    "month_label": CALENDAR_MONTHS[row["month"].month],
                    "total_sales": 0,
                    "total_purchases": 0,
                    "sales_count": 0,
                    "purchases_count": 0,
                }
            if row["movement_type"] in ("sale", "sales_return"):
                pivot[key]["total_sales"] += float(row["total_value"] or 0)
                pivot[key]["sales_count"] += row["row_count"]
            elif row["movement_type"] in ("purchase", "purchase_return"):
                pivot[key]["total_purchases"] += float(row["total_value"] or 0)
                pivot[key]["purchases_count"] += row["row_count"]

        return Response({
            "summary": list(pivot.values()),
        })


class TransactionTypeBreakdownView(APIView):
    """
    GET /api/transactions/type-breakdown/
    Returns total value and count grouped by movement type.
    Useful for the movement-type distribution chart.

    Query params:
        date_from=YYYY-MM-DD
        date_to=YYYY-MM-DD
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
                    "label": dict(MaterialMovement.MovementType.choices).get(
                        row["movement_type"], row["movement_type"]
                    ),
                    "count": row["count"],
                    "total_in": float(row["total_in"] or 0),
                    "total_out": float(row["total_out"] or 0),
                }
                for row in breakdown
            ]
        })


class TransactionBranchBreakdownView(APIView):
    """
    GET /api/transactions/branch-breakdown/
    Returns sales totals grouped by branch_name.

    Query params:
        movement_type=sale  (default)
        date_from / date_to
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        movement_type = request.query_params.get("movement_type", "sale")

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
            .annotate(
                count=Count("id"),
                total_out=Sum("total_out"),
            )
            .order_by("-total_out")
        )

        return Response({
            "movement_type": movement_type,
            "branches": [
                {
                    "branch": row["branch_name"] or "Unknown",
                    "count": row["count"],
                    "total": float(row["total_out"] or 0),
                }
                for row in breakdown
            ],
        })
