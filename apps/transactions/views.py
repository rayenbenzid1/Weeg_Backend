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

# Arabic movement type groups for aggregation
SALE_TYPES            = ["ف بيع"]
PURCHASE_TYPES        = ["ف شراء"]
RETURN_SALE_TYPES     = ["مردودات بيع"]
RETURN_PURCHASE_TYPES = ["مردود شراء"]

# Maps raw Arabic branch_name (stored in DB) → English display name
# Must align with the English names used in InventoryBranchSummaryView
BRANCH_NAME_MAP = {
    "مخزن صالة عرض الكريمية":          "Al-Karimia",
    "مخزن صالة عرض الدهماني":          "Dahmani",
    "مخزن صالة عرض جنزور":             "Janzour",
    "مخزن صالة عرض مصراتة":            "Misrata",
    "مخزن المزرعة":                    "Al-Mazraa",
    "مخزن بنغازي":                     "Benghazi",
    "مخزن الأنظمة المتكاملة - الكريمية": "Al-Karimia",
}

def _en_branch(arabic_name: str | None) -> str:
    if not arabic_name:
        return "Unknown"
    return BRANCH_NAME_MAP.get(arabic_name.strip(), arabic_name.strip())


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

        # ── Totaux KPI ───────────────────────────────────────────────────────────
        # Ventes  (ف بيع, مردودات بيع)   → valeur réelle dans total_out
        # Achats  (ف شراء, مردود شراء, ادخال رئيسي) → valeur réelle dans total_in
        # ── Totaux KPI ───────────────────────────────────────────────────────────
        # Excel اجمالي الاخراجات = 9,341,919,552 → ventes ف بيع → total_out
        # Excel اجمالي الادخلات  = 8,193,107,933 → achats ف شراء → total_in (فاتورة شراء uniquement)
        sale_total_out = (
            qs.filter(movement_type="ف بيع")
            .aggregate(v=Sum("total_out"))["v"] or 0
        )
        purchase_total_in = (
            qs.filter(movement_type="ف شراء")
            .aggregate(v=Sum("total_in"))["v"] or 0
        )
        totals = {
            "total_in_value":  float(purchase_total_in),   # اجمالي الادخلات  — ف شراء only
            "total_out_value": float(sale_total_out),       # اجمالي الاخراجات — ف بيع only
        }

        total_count = qs.count()
        page      = max(1, int(request.query_params.get("page", 1)))
        page_size = min(200, max(1, int(request.query_params.get("page_size", 50))))
        start     = (page - 1) * page_size
        qs_page   = qs[start: start + page_size]

        return Response({
            "count":       total_count,
            "page":        page,
            "page_size":   page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "totals": totals,
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
            return Response(
                {"error": "Movement not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(MovementDetailSerializer(movement).data)


class TransactionMovementTypesView(APIView):
    """
    GET /api/transactions/movement-types/
    Returns distinct movement_type values for this company.
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
    Returns distinct branch names (English) for this company.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_branches = (
            MaterialMovement.objects
            .filter(company=request.user.company)
            .exclude(branch_name__isnull=True)
            .exclude(branch_name="")
            .values_list("branch_name", flat=True)
            .distinct()
        )
        english_branches = sorted({_en_branch(b) for b in raw_branches})
        return Response({"branches": english_branches})


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
        date_from = request.query_params.get("date_from")  # ← AJOUT
        date_to  = request.query_params.get("date_to")  
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)
        if year and not date_from and not date_to:   # ← seulement si pas de dates
            try:
                qs = qs.filter(movement_date__year=int(year))
            except ValueError:
                pass

        monthly = (
            qs.annotate(month=TruncMonth("movement_date"))
            .values("month", "movement_type")
            .annotate(
                total_out_value=Sum("total_out"),
                total_in_value=Sum("total_in"),
                row_count=Count("id"),
            )
            .order_by("month")
        )

        pivot = {}
        for row in monthly:
            key = row["month"].strftime("%Y-%m")
            if key not in pivot:
                pivot[key] = {
                    "year":            row["month"].year,
                    "month":           row["month"].month,
                    "month_label":     CALENDAR_MONTHS[row["month"].month],
                    "total_sales":     0,
                    "total_purchases": 0,
                    "sales_count":     0,
                    "purchases_count": 0,
                }
            mt = row["movement_type"]
            if mt in SALE_TYPES or mt in RETURN_SALE_TYPES:
                # Sales go OUT → total_out
                pivot[key]["total_sales"]  += float(row["total_out_value"] or 0)
                pivot[key]["sales_count"]  += row["row_count"]
            elif mt in PURCHASE_TYPES or mt in RETURN_PURCHASE_TYPES:
                # Purchases come IN → total_in (اجمالي الادخلات)
                pivot[key]["total_purchases"] += float(row["total_in_value"] or 0)
                pivot[key]["purchases_count"] += row["row_count"]

        return Response({"summary": list(pivot.values())})


class TransactionTypeBreakdownView(APIView):
    """
    GET /api/transactions/type-breakdown/
    Totals grouped by movement_type (raw Arabic label).
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

    # Movement types where value is stored in total_in (not total_out)
    PURCHASE_TYPES = {"ف شراء", "مردود شراء"}
    def get(self, request):
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

        # ── Use total_in for purchase-type movements, total_out for sales ──
        value_field = "total_in" if movement_type in self.PURCHASE_TYPES else "total_out"

        breakdown = (
            qs.values("branch_name")
            .annotate(count=Count("id"), total=Sum(value_field))
            .order_by("-total")
        )

        return Response({
            "movement_type": movement_type,
            "branches": [
                {
                    "branch": _en_branch(row["branch_name"]),
                    "count":  row["count"],
                    "total":  float(row["total"] or 0),
                }
                for row in breakdown
            ],
        })
# ── This must be a TOP-LEVEL class, NOT nested inside TransactionBranchBreakdownView ──

class TransactionBranchMonthlyView(APIView):
    """
    GET /api/transactions/branch-monthly/
    Monthly sales breakdown per branch — powers the per-branch line chart.

    Query params:
        movement_type=<arabic_value>  — default: "ف بيع"
        year=<int>
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        movement_type = request.query_params.get("movement_type", "ف بيع")
        year      = request.query_params.get("year")
        date_from = request.query_params.get("date_from")
        date_to   = request.query_params.get("date_to")

        qs = MaterialMovement.objects.filter(
            company=request.user.company,
            movement_type=movement_type,
        )

        # Priority: date_from/date_to over year
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)
        if year and not date_from and not date_to:
            try:
                qs = qs.filter(movement_date__year=int(year))
            except ValueError:
                pass

        rows = (
            qs.annotate(month=TruncMonth("movement_date"))
            .values("month", "branch_name")
            .annotate(total=Sum("total_out"), count=Count("id"))
            .order_by("month", "branch_name")
        )

        pivot = {}
        branches: set[str] = set()

        for row in rows:
            key = row["month"].strftime("%Y-%m")
            branch = _en_branch(row["branch_name"])
            branches.add(branch)
            if key not in pivot:
                pivot[key] = {
                    "month":     CALENDAR_MONTHS[row["month"].month],
                    "year":      row["month"].year,
                    "_sort_key": key,
                }
            pivot[key][branch] = float(row["total"] or 0)

        sorted_data = sorted(pivot.values(), key=lambda x: x["_sort_key"])
        for item in sorted_data:
            item.pop("_sort_key", None)

        return Response({
            "movement_type": movement_type,
            "branches":      sorted(list(branches)),
            "monthly_data":  sorted_data,
        })