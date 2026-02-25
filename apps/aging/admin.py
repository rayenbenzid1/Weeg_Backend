from django.contrib import admin
from .models import AgingReceivable


@admin.register(AgingReceivable)
class AgingReceivableAdmin(admin.ModelAdmin):
    list_display = [
        "account_code", "account", "report_date",
        "total", "risk_score_display", "company",
    ]
    list_filter = ["company", "report_date"]
    search_fields = ["account", "account_code"]
    readonly_fields = ["id", "total", "created_at", "updated_at"]
    ordering = ["-total", "account"]
    list_per_page = 50
    date_hierarchy = "report_date"

    def risk_score_display(self, obj):
        return obj.risk_score
    risk_score_display.short_description = "Risk"

    fieldsets = (
        ("Reference", {
            "fields": ("id", "company", "customer", "account", "account_code", "report_date"),
        }),
        ("Aging Buckets (LYD)", {
            "fields": (
                "current", "d1_30", "d31_60", "d61_90", "d91_120",
                "d121_150", "d151_180", "d181_210", "d211_240",
                "d241_270", "d271_300", "d301_330", "over_330",
            ),
        }),
        ("Total", {
            "fields": ("total",),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
