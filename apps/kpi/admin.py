"""
apps/kpi/admin.py
-----------------
Django admin configuration for the KPI application.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import KPISnapshot, RiskyCustomerSnapshot


class RiskyCustomerInline(admin.TabularInline):
    model = RiskyCustomerSnapshot
    extra = 0
    readonly_fields = (
        "rank", "account_code", "customer_name",
        "total", "current", "overdue_total",
        "risk_score", "overdue_percentage", "dmp_days",
    )
    fields = readonly_fields
    can_delete = False
    max_num = 5
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(KPISnapshot)
class KPISnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "report_date",
        "computed_at",
        "taux_clients_credit_display",
        "taux_credit_total_display",
        "taux_impayes_display",
        "dmp_display",
        "taux_recouvrement_display",
        "credit_customers",
        "total_customers",
    )
    list_filter = ("report_date",)
    readonly_fields = (
        "computed_at",
        "report_date",
        "taux_clients_credit",
        "taux_credit_total",
        "taux_impayes",
        "dmp",
        "taux_recouvrement",
        "total_customers",
        "credit_customers",
        "grand_total_receivables",
        "overdue_amount",
        "ca_credit",
        "ca_total",
    )
    inlines = [RiskyCustomerInline]
    ordering = ["-computed_at"]

    def taux_clients_credit_display(self, obj):
        color = "green" if obj.taux_clients_credit >= 50 else "orange"
        return format_html(
            '<span style="color:{}">{:.1f}%</span>', color, obj.taux_clients_credit
        )
    taux_clients_credit_display.short_description = "Taux clients crédit"

    def taux_credit_total_display(self, obj):
        color = "green" if obj.taux_credit_total <= 85 else "red"
        return format_html(
            '<span style="color:{}">{:.1f}%</span>', color, obj.taux_credit_total
        )
    taux_credit_total_display.short_description = "Taux crédit total"

    def taux_impayes_display(self, obj):
        color = "green" if obj.taux_impayes <= 20 else "red"
        return format_html(
            '<span style="color:{}">{:.1f}%</span>', color, obj.taux_impayes
        )
    taux_impayes_display.short_description = "Taux impayés"

    def dmp_display(self, obj):
        color = "green" if obj.dmp <= 30 else ("orange" if obj.dmp <= 90 else "red")
        return format_html(
            '<span style="color:{}">{:.0f} j</span>', color, obj.dmp
        )
    dmp_display.short_description = "DMP"

    def taux_recouvrement_display(self, obj):
        color = "green" if obj.taux_recouvrement >= 70 else "red"
        return format_html(
            '<span style="color:{}">{:.1f}%</span>', color, obj.taux_recouvrement
        )
    taux_recouvrement_display.short_description = "Taux recouvrement"


@admin.register(RiskyCustomerSnapshot)
class RiskyCustomerSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "rank",
        "customer_name",
        "account_code",
        "total",
        "overdue_total",
        "risk_badge",
        "dmp_days",
        "snapshot",
    )
    list_filter = ("risk_score", "snapshot__report_date")
    search_fields = ("customer_name", "account_code")
    ordering = ["snapshot", "rank"]

    def risk_badge(self, obj):
        colors = {
            "low":      ("green",  "Faible"),
            "medium":   ("orange", "Moyen"),
            "high":     ("darkorange", "Élevé"),
            "critical": ("red",    "Critique"),
        }
        color, label = colors.get(obj.risk_score, ("gray", obj.risk_score))
        return format_html(
            '<span style="color:{}; font-weight:bold">{}</span>', color, label
        )
    risk_badge.short_description = "Risque"