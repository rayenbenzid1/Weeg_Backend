"""
apps/kpi/views_stock.py
-----------------------
Stock KPIs:
  2.1 Niveau de stock (aggregated)
  2.2 Taux de rotation du stock
  2.3 Produits à faible rotation
  2.4 Rupture de stock (zero stock products)
  2.5 Taux de couverture du stock

FIX: Join sales → inventory by material_name (NOT material_code).
     Movements file uses short codes (e.g. "EC0020") while inventory
     uses full codes (e.g. "AS-FD-In-AD-EC0020") → code join = 0% match.
     Product names are identical in both files → use name as join key.
"""

import logging
from decimal import Decimal
from datetime import date

from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

SALE_TYPES = ["ف بيع"]
LOW_ROTATION_THRESHOLD = 0.5
DEFAULT_LEAD_TIME_DAYS = 14
SAFETY_FACTOR = 0.5


class StockKPIView(APIView):
    """
    GET /api/kpi/stock/

    Query params:
        snapshot_date=YYYY-MM-DD       — inventory snapshot (default: latest)
        year=<int>                     — year for sales data (default: snapshot year)
        low_rotation_threshold=<float> — rotation threshold (default: 0.5)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.inventory.models import InventorySnapshot
        from apps.transactions.models import MaterialMovement

        company = request.user.company

        # ── Resolve snapshot date ────────────────────────────────────────────
        snapshot_date_param = request.query_params.get("snapshot_date")
        if snapshot_date_param:
            snapshot_date = date.fromisoformat(snapshot_date_param)
        else:
            latest = (
                InventorySnapshot.objects
                .filter(company=company)
                .order_by("-snapshot_date")
                .values_list("snapshot_date", flat=True)
                .first()
            )
            snapshot_date = latest if latest else date.today()

        year = int(request.query_params.get("year", snapshot_date.year))
        rotation_threshold = float(
            request.query_params.get("low_rotation_threshold", LOW_ROTATION_THRESHOLD)
        )

        period_from = date(year, 1, 1)
        period_to   = date(year, 12, 31)
        n_days = (period_to - period_from).days + 1

        # ── Inventory snapshot ───────────────────────────────────────────────
        inv_qs = InventorySnapshot.objects.filter(
            company=company,
            snapshot_date=snapshot_date,
        ).select_related("product")

        # ── Sales grouped by material_name (FIX: not material_code) ─────────
        sales_by_name = {}
        sales_qs = (
            MaterialMovement.objects
            .filter(
                company=company,
                movement_type__in=SALE_TYPES,
                movement_date__gte=period_from,
                movement_date__lte=period_to,
            )
            .values("material_name")
            .annotate(
                qty_sold=Coalesce(Sum("qty_out"), Decimal("0")),
                revenue=Coalesce(Sum("total_out"), Decimal("0")),
            )
        )
        for row in sales_qs:
            key = (row["material_name"] or "").strip().lower()
            if key:
                sales_by_name[key] = {
                    "qty_sold": float(row["qty_sold"]),
                    "revenue":  float(row["revenue"]),
                }

        # ── Per-product KPIs ─────────────────────────────────────────────────
        all_products      = []
        zero_stock        = []
        low_rotation      = []
        total_stock_value = 0.0
        total_stock_qty   = 0.0

        for snap in inv_qs:
            stock_qty  = float(snap.total_qty)
            stock_val  = float(snap.total_value)
            cost_price = float(snap.cost_price)

            total_stock_value += stock_val
            total_stock_qty   += stock_qty

            # Join by name (normalized)
            name_key = snap.product.product_name.strip().lower()
            sales    = sales_by_name.get(name_key, {"qty_sold": 0.0, "revenue": 0.0})
            qty_sold = sales["qty_sold"]

            monthly_usage = qty_sold / 12.0
            safety_stock  = monthly_usage * SAFETY_FACTOR
            min_stock     = int(round(monthly_usage * (DEFAULT_LEAD_TIME_DAYS / 30.0) + safety_stock))
            max_stock     = int(round(monthly_usage * 3))
            reorder_qty   = max(0.0, max_stock - stock_qty)

            rotation_rate   = round(qty_sold / stock_qty, 4) if stock_qty > 0 else 0.0
            avg_daily_sales = qty_sold / n_days if n_days > 0 else 0
            coverage_days   = round(stock_qty / avg_daily_sales, 1) if avg_daily_sales > 0 else None
            days_of_stock   = (
                round((stock_qty / monthly_usage) * 30)
                if monthly_usage > 0 else None
            )

            if stock_qty == 0:
                stock_status = "out"
            elif min_stock > 0 and stock_qty <= min_stock:
                stock_status = "critical"
            elif min_stock > 0 and stock_qty <= min_stock * 1.5:
                stock_status = "low"
            else:
                stock_status = "ok"

            product_data = {
                "material_code":  snap.product.product_code,
                "product_name":   snap.product.product_name,
                "category":       snap.product.category or "",
                "stock_qty":      stock_qty,
                "stock_value":    stock_val,
                "cost_price":     cost_price,
                "qty_sold":       qty_sold,
                "monthly_usage":  round(monthly_usage, 2),
                "revenue":        sales["revenue"],
                "rotation_rate":  rotation_rate,
                "coverage_days":  coverage_days,
                "min_stock":      min_stock,
                "max_stock":      max_stock,
                "reorder_qty":    round(reorder_qty, 0),
                "days_of_stock":  days_of_stock,
                "status":         stock_status,
            }
            all_products.append(product_data)

            if stock_qty == 0:
                zero_stock.append({
                    "material_code": snap.product.product_code,
                    "product_name":  snap.product.product_name,
                    "category":      snap.product.category or "",
                    "qty_sold":      qty_sold,
                })

            if stock_qty > 0 and rotation_rate < rotation_threshold:
                low_rotation.append({
                    "material_code": snap.product.product_code,
                    "product_name":  snap.product.product_name,
                    "category":      snap.product.category or "",
                    "stock_qty":     stock_qty,
                    "stock_value":   stock_val,
                    "qty_sold":      qty_sold,
                    "rotation_rate": rotation_rate,
                    "coverage_days": coverage_days,
                })

        low_rotation.sort(key=lambda x: -x["stock_value"])

        top_rotation = sorted(
            [p for p in all_products if p["stock_qty"] > 0],
            key=lambda x: -x["rotation_rate"]
        )[:20]

        products_with_stock = [p for p in all_products if p["stock_qty"] > 0]
        avg_rotation = (
            sum(p["rotation_rate"] for p in products_with_stock) / len(products_with_stock)
            if products_with_stock else 0.0
        )

        return Response({
            "snapshot_date": str(snapshot_date),
            "year":          year,
            "period":        {"from": str(period_from), "to": str(period_to)},
            "stock_summary": {
                "total_products":     len(all_products),
                "total_stock_qty":    round(total_stock_qty, 2),
                "total_stock_value":  round(total_stock_value, 2),
                "zero_stock_count":   len(zero_stock),
                "low_rotation_count": len(low_rotation),
                "critical_count":     sum(1 for p in all_products if p["status"] == "critical"),
                "low_count":          sum(1 for p in all_products if p["status"] == "low"),
                "avg_rotation_rate":  round(avg_rotation, 4),
            },
            "top_rotation_products": top_rotation,
            "low_rotation_products": low_rotation[:50],
            "zero_stock_products":   zero_stock,
            "coverage_at_risk": sorted(
                [p for p in products_with_stock if p["coverage_days"] is not None],
                key=lambda x: x["coverage_days"]
            )[:20],
            "reorder_list": sorted(
                all_products,
                key=lambda x: {"out": 0, "critical": 1, "low": 2, "ok": 3}.get(x["status"], 4)
            ),
        })