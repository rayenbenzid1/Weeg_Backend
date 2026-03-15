"""
apps/kpi/views_sales.py
-----------------------
Sales KPIs:
  1.1 Total Revenue (CA)
  1.2 Sales Evolution (%)
  1.3 Top products (qty + revenue)
  1.4 Sales by period (monthly)
  1.5 Gross margin per product (%)
  1.6 Top clients
  1.7 Average sales velocity

Margin formula
──────────────
  gross_profit = (price_out - balance_price) * qty_out
               = (سعر الاخراجات - سعر الرصيد) * كمية الاخراجات

  margin_pct   = (gross_profit / total_revenue) * 100

Where:
  price_out     = unit sale price   (col سعر الاخراجات)
  balance_price = unit cost price   (col سعر الرصيد)
  qty_out       = quantity sold     (col كمية الاخراجات)
  total_revenue = price_out × qty_out = total_out
"""

import logging
from decimal import Decimal
from datetime import date

from django.db.models import Sum, Count, Q, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce, TruncMonth
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

SALE_TYPES     = ["ف بيع"]
PURCHASE_TYPES = ["ف شراء", "ادخال رئيسي"]

CALENDAR_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class SalesKPIView(APIView):
    """
    GET /api/kpi/sales/

    Query params:
        year=<int>           — filter year (default: current year or latest data year)
        date_from=YYYY-MM-DD
        date_to=YYYY-MM-DD
        branch=<str>         — optional exact branch filter
        top_n=<int>          — number of top products/customers (default: 10)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.transactions.models import MaterialMovement

        company = request.user.company

        # ── Resolve date range ────────────────────────────────────────────────
        year_param = request.query_params.get("year")
        date_from  = request.query_params.get("date_from")
        date_to    = request.query_params.get("date_to")
        branch     = (request.query_params.get("branch") or "").strip()
        top_n      = min(50, max(1, int(request.query_params.get("top_n", 10))))

        base_qs = MaterialMovement.objects.filter(company=company)
        if branch:
            base_qs = base_qs.filter(branch__name=branch)

        # Resolve year: use param, else infer from latest data
        if year_param:
            year        = int(year_param)
            period_from = date(year, 1, 1)
            period_to   = date(year, 12, 31)
        elif date_from and date_to:
            period_from = date.fromisoformat(date_from)
            period_to   = date.fromisoformat(date_to)
            year        = period_from.year
        else:
            latest = (
                base_qs.order_by("-movement_date")
                .values_list("movement_date", flat=True)
                .first()
            )
            year        = latest.year if latest else date.today().year
            period_from = date(year, 1, 1)
            period_to   = date(year, 12, 31)

        # Previous year for evolution calculation
        prev_from = date(year - 1, 1, 1)
        prev_to   = date(year - 1, 12, 31)

        # ── Sales querysets ───────────────────────────────────────────────────
        sales_qs     = base_qs.filter(movement_type__in=SALE_TYPES)
        sales_period = sales_qs.filter(movement_date__gte=period_from, movement_date__lte=period_to)
        sales_prev   = sales_qs.filter(movement_date__gte=prev_from,   movement_date__lte=prev_to)

        zero_decimal = Value(
            Decimal("0.0000"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )

        # ── Gross profit expression ───────────────────────────────────────────
        # Formula: (سعر الاخراجات - سعر الرصيد) × كمية الاخراجات
        #        = (price_out     - balance_price) × qty_out
        profit_expression = ExpressionWrapper(
            (
                Coalesce(F("price_out"),     zero_decimal)
                - Coalesce(F("balance_price"), zero_decimal)
            )
            * Coalesce(F("qty_out"), zero_decimal),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
        sum_price_out_x_qty = ExpressionWrapper(
            Coalesce(F("price_out"), zero_decimal) * Coalesce(F("qty_out"), zero_decimal),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )

        sum_balance_price_x_qty = ExpressionWrapper(
            Coalesce(F("balance_price"), zero_decimal) * Coalesce(F("qty_out"), zero_decimal),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
        # ── 1.1 Total Revenue ─────────────────────────────────────────────────
        ca_total = float(
            sales_period.aggregate(ca=Coalesce(Sum("total_out"), Decimal("0")))["ca"]
        )
        ca_prev = float(
            sales_prev.aggregate(ca=Coalesce(Sum("total_out"), Decimal("0")))["ca"]
        )

        # ── 1.2 Sales Evolution % ─────────────────────────────────────────────
        if ca_prev > 0:
            sales_evolution = round(((ca_total - ca_prev) / ca_prev) * 100, 2)
        else:
            sales_evolution = None  # No previous year data

        # ── 1.3 Top Products ──────────────────────────────────────────────────
        top_products_qs = (
            sales_period
            .values("material_code", "material_name")
            .annotate(
                total_revenue=Coalesce(Sum("total_out"),  Decimal("0")),
                total_qty=Coalesce(Sum("qty_out"),        Decimal("0")),
                transaction_count=Count("id"),
            )
            .order_by("-total_revenue")[:top_n]
        )

        top_products = [
            {
                "material_code":     row["material_code"],
                "material_name":     row["material_name"],
                "total_revenue":     float(row["total_revenue"]),
                "total_qty":         float(row["total_qty"]),
                "transaction_count": row["transaction_count"],
                "revenue_share":     round(float(row["total_revenue"]) / ca_total * 100, 2)
                                     if ca_total > 0 else 0.0,
            }
            for row in top_products_qs
        ]

        # ── 1.4 Monthly Sales ─────────────────────────────────────────────────
        monthly_qs = (
            sales_period
            .annotate(month=TruncMonth("movement_date"))
            .values("month")
            .annotate(
                total_revenue=Coalesce(Sum("total_out"), Decimal("0")),
                total_qty=Coalesce(Sum("qty_out"),       Decimal("0")),
                count=Count("id"),
            )
            .order_by("month")
        )

        monthly_sales = [
            {
                "year":          row["month"].year,
                "month":         row["month"].month,
                "month_label":   CALENDAR_MONTHS[row["month"].month],
                "total_revenue": float(row["total_revenue"]),
                "total_qty":     float(row["total_qty"]),
                "count":         row["count"],
            }
            for row in monthly_qs
        ]

        # ── 1.5 Product Margins ───────────────────────────────────────────────
        # gross_profit = (price_out - balance_price) × qty_out
        # margin_pct   = (gross_profit / total_revenue) × 100
        top_margins_qs = (
            sales_period
            .values("material_code", "material_name")
            .annotate(
                total_revenue=Coalesce(Sum("total_out"), Decimal("0")),
                total_qty=Coalesce(Sum("qty_out"),       Decimal("0")),
                total_profit=Coalesce(Sum(profit_expression), Decimal("0")),
                total_price_out_x_qty=Coalesce(Sum(sum_price_out_x_qty),     Decimal("0")),
                total_balance_price_x_qty=Coalesce(Sum(sum_balance_price_x_qty), Decimal("0"))
            )
            .order_by("-total_revenue")
        )

        product_margins = []
        for row in top_margins_qs:
            total_revenue = float(row["total_revenue"] or 0)
            total_profit  = float(row["total_profit"]  or 0)
            total_qty     = float(row["total_qty"]     or 0)

            total_price_out_x_qty     = float(row["total_price_out_x_qty"]     or 0)
            total_balance_price_x_qty = float(row["total_balance_price_x_qty"] or 0)

            product_margins.append({
                "material_code":    row["material_code"],
                "material_name":    row["material_name"],
                "total_revenue":    round(total_revenue, 2),
                "total_qty":        total_qty,
                "total_profit":     round(total_profit, 2),   # gross profit in LYD
                "margin_pct":       round((total_profit / total_revenue) * 100, 2)
                                    if total_revenue > 0 else None,
                # ── Formula components (for UI transparency) ──────────────────
                "total_price_out_x_qty":     round(total_price_out_x_qty, 2),     # Σ(سعر الاخراجات × qty)
                "total_balance_price_x_qty": round(total_balance_price_x_qty, 2), # Σ(سعر الرصيد × qty)
            })

        # ── 1.6 Top Clients ───────────────────────────────────────────────────
        top_clients_qs = (
            sales_period
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .values("customer_name")
            .annotate(
                total_revenue=Coalesce(Sum("total_out"), Decimal("0")),
                total_profit=Coalesce(Sum(profit_expression), Decimal("0")),
                transaction_count=Count("id"),
            )
            .order_by("-total_profit", "-total_revenue")[:top_n]
        )

        top_clients = [
            {
                "customer_name":     row["customer_name"],
                "total_revenue":     float(row["total_revenue"]),
                "total_profit":      float(row["total_profit"] or 0),
                "transaction_count": row["transaction_count"],
                "revenue_share":     round(float(row["total_revenue"]) / ca_total * 100, 2)
                                     if ca_total > 0 else 0.0,
            }
            for row in top_clients_qs
        ]

        # ── 1.7 Sales Velocity ────────────────────────────────────────────────
        n_days = max(1, (period_to - period_from).days + 1)

        total_qty_sold    = float(sales_period.aggregate(qty=Coalesce(Sum("qty_out"), Decimal("0")))["qty"])
        avg_daily_qty     = total_qty_sold / n_days if n_days > 0 else 0
        avg_daily_revenue = ca_total / n_days if n_days > 0 else 0

        avg_days_per_product = []
        for p in top_products[:10]:
            daily_qty     = p["total_qty"]     / n_days if n_days > 0 else 0
            daily_revenue = p["total_revenue"] / n_days if n_days > 0 else 0
            avg_days_per_product.append({
                "material_code":       p["material_code"],
                "material_name":       p["material_name"],
                "avg_daily_qty":       round(daily_qty, 4),
                "avg_daily_revenue":   round(daily_revenue, 2),
                "days_to_sell_100_units": round(100 / daily_qty, 1) if daily_qty > 0 else None,
            })

        return Response({
            "year":        year,
            "period":      {"from": str(period_from), "to": str(period_to)},
            "prev_period": {"from": str(prev_from),   "to": str(prev_to)},

            # 1.1 Revenue
            "ca": {
                "total":    round(ca_total, 2),
                "previous": round(ca_prev, 2),
                "label":    "Total Revenue",
                "unit":     "LYD",
            },

            # 1.2 Evolution
            "sales_evolution": {
                "value": sales_evolution,
                "label": "Sales Evolution",
                "unit":  "%",
                "is_up": sales_evolution >= 0 if sales_evolution is not None else None,
            },

            # 1.3 Top products
            "top_products": top_products,

            # 1.4 Monthly trend
            "monthly_sales": monthly_sales,

            # 1.5 Product margins
            # Formula: gross_profit = (price_out - balance_price) * qty_out
            #          margin_pct   = (gross_profit / total_revenue) * 100
            "margin_formula": "(سعر الاخراجات - سعر الرصيد) × كمية الاخراجات",
            "product_margins": product_margins,

            # 1.6 Top clients
            "top_clients": top_clients,

            # 1.7 Sales velocity
            "sales_velocity": {
                "avg_daily_revenue": round(avg_daily_revenue, 2),
                "avg_daily_qty":     round(avg_daily_qty, 4),
                "total_days":        n_days,
                "by_product":        avg_days_per_product,
            },
        })