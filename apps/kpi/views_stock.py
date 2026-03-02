"""
apps/kpi/views_stock.py
-----------------------
Stock KPIs:
  2.1 Niveau de stock (already in /inventory/ — aggregated here)
  2.2 Taux de rotation du stock
  2.3 Produits à faible rotation
  2.4 Rupture de stock (zero stock products)
  2.5 Taux de couverture du stock
"""

import logging
from decimal import Decimal
from datetime import date

from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

SALE_TYPES = ["ف بيع"]
LOW_ROTATION_THRESHOLD = 0.5  # Less than 0.5 rotations/year = low rotation


class StockKPIView(APIView):
    """
    GET /api/kpi/stock/

    Query params:
        snapshot_date=YYYY-MM-DD  — inventory snapshot (default: latest)
        year=<int>                — year for sales data (default: snapshot year)
        low_rotation_threshold=<float>  — rotation rate below which product is flagged (default: 0.5)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.inventory.models import InventorySnapshot
        from apps.transactions.models import MaterialMovement

        company = request.user.company

        # ── Resolve snapshot date ──────────────────────────────────────────────
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

        # ── Inventory snapshot ────────────────────────────────────────────────
        inv_qs = InventorySnapshot.objects.filter(
            company=company,
            snapshot_date=snapshot_date,
        ).select_related("product")

        # ── Sales data for the year ────────────────────────────────────────────
        sales_by_product = {}
        sales_qs = (
            MaterialMovement.objects
            .filter(
                company=company,
                movement_type__in=SALE_TYPES,
                movement_date__gte=period_from,
                movement_date__lte=period_to,
            )
            .values("material_code")
            .annotate(
                qty_sold=Coalesce(Sum("qty_out"), Decimal("0")),
                revenue=Coalesce(Sum("total_out"), Decimal("0")),
            )
        )
        for row in sales_qs:
            sales_by_product[row["material_code"]] = {
                "qty_sold": float(row["qty_sold"]),
                "revenue":  float(row["revenue"]),
            }

        # ── Compute per-product KPIs ──────────────────────────────────────────
        all_products     = []
        zero_stock       = []
        low_rotation     = []
        total_stock_value = 0.0
        total_stock_qty   = 0.0

        for snap in inv_qs:
            code       = snap.product.product_code
            stock_qty  = float(snap.total_qty)
            stock_val  = float(snap.total_value)
            cost_price = float(snap.cost_price)

            total_stock_value += stock_val
            total_stock_qty   += stock_qty

            sales = sales_by_product.get(code, {"qty_sold": 0.0, "revenue": 0.0})
            qty_sold = sales["qty_sold"]

            # 2.2 Taux de rotation = qty vendue / stock moyen
            # Approximation: stock actuel = stock moyen (pas d'historique mensuel)
            rotation_rate = round(qty_sold / stock_qty, 4) if stock_qty > 0 else 0.0

            # 2.5 Taux de couverture = stock / (ventes journalières moyennes)
            avg_daily_sales = qty_sold / n_days if n_days > 0 else 0
            coverage_days   = round(stock_qty / avg_daily_sales, 1) if avg_daily_sales > 0 else None

            product_data = {
                "material_code":  code,
                "product_name":   snap.product.product_name,
                "category":       snap.product.category,
                "stock_qty":      stock_qty,
                "stock_value":    stock_val,
                "cost_price":     cost_price,
                "qty_sold":       qty_sold,
                "revenue":        sales["revenue"],
                "rotation_rate":  rotation_rate,
                "coverage_days":  coverage_days,
            }
            all_products.append(product_data)

            # 2.4 Zero stock
            if stock_qty == 0:
                zero_stock.append({
                    "material_code": code,
                    "product_name":  snap.product.product_name,
                    "category":      snap.product.category,
                    "qty_sold":      qty_sold,
                })

            # 2.3 Low rotation (has stock but sells slowly)
            if stock_qty > 0 and rotation_rate < rotation_threshold:
                low_rotation.append({
                    "material_code": code,
                    "product_name":  snap.product.product_name,
                    "category":      snap.product.category,
                    "stock_qty":     stock_qty,
                    "stock_value":   stock_val,
                    "qty_sold":      qty_sold,
                    "rotation_rate": rotation_rate,
                    "coverage_days": coverage_days,
                })

        # Sort low rotation by stock_value DESC (highest immobilized capital first)
        low_rotation.sort(key=lambda x: -x["stock_value"])

        # Top rotation products (fastest moving)
        top_rotation = sorted(
            [p for p in all_products if p["stock_qty"] > 0],
            key=lambda x: -x["rotation_rate"]
        )[:20]

        # ── Summary stats ─────────────────────────────────────────────────────
        products_with_stock = [p for p in all_products if p["stock_qty"] > 0]
        avg_rotation = (
            sum(p["rotation_rate"] for p in products_with_stock) / len(products_with_stock)
            if products_with_stock else 0.0
        )

        total_products = len(all_products)
        zero_stock_count = len(zero_stock)
        low_rotation_count = len(low_rotation)

        return Response({
            "snapshot_date": str(snapshot_date),
            "year":          year,
            "period":        {"from": str(period_from), "to": str(period_to)},

            # 2.1 Niveau de stock (summary)
            "stock_summary": {
                "total_products":    total_products,
                "total_stock_qty":   round(total_stock_qty, 2),
                "total_stock_value": round(total_stock_value, 2),
                "zero_stock_count":  zero_stock_count,
                "low_rotation_count": low_rotation_count,
                "avg_rotation_rate": round(avg_rotation, 4),
            },

            # 2.2 Taux de rotation — top movers
            "top_rotation_products": top_rotation,

            # 2.3 Produits à faible rotation
            "low_rotation_products": low_rotation[:50],

            # 2.4 Rupture de stock
            "zero_stock_products": zero_stock,

            # 2.5 Taux de couverture — products sorted by shortest coverage
            "coverage_at_risk": sorted(
                [p for p in products_with_stock if p["coverage_days"] is not None],
                key=lambda x: x["coverage_days"]
            )[:20],
        })