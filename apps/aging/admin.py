from django.contrib import admin
from .models import AgingReceivable, AgingSnapshot


@admin.register(AgingSnapshot)
class AgingSnapshotAdmin(admin.ModelAdmin):
    list_display = ["id", "company", "report_date", "source_file", "uploaded_by", "uploaded_at"]
    list_filter = ["company", "uploaded_at"]
    search_fields = ["source_file"]
    readonly_fields = ["id", "uploaded_at"]
    ordering = ["-uploaded_at"]
    list_per_page = 50


@admin.register(AgingReceivable)
class AgingReceivableAdmin(admin.ModelAdmin):
    list_display = [
        "account_code", "account", "created_at",
        "total", "risk_score_display", "company",
    ]
    list_filter = ["company", "snapshot", "created_at"]
    search_fields = ["account", "account_code"]
    readonly_fields = ["id", "total", "created_at", "updated_at"]
    ordering = ["-total", "account"]
    list_per_page = 50
    date_hierarchy = "created_at"

    def risk_score_display(self, obj):
        return obj.risk_score
    risk_score_display.short_description = "Risk"

    fieldsets = (
        ("Reference", {
            "fields": ("id", "snapshot", "company", "customer", "account", "account_code"),
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
