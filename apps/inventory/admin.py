from django.contrib import admin
from .models import InventorySnapshot


@admin.register(InventorySnapshot)
class InventorySnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "product", "snapshot_date", "total_qty",
        "total_value", "cost_price", "company",
    ]
    list_filter = ["company", "snapshot_date"]
    search_fields = [
        "product__product_code", "product__product_name",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-snapshot_date", "product__product_name"]
    list_per_page = 50
    date_hierarchy = "snapshot_date"

    fieldsets = (
        ("Reference", {
            "fields": ("id", "company", "product", "snapshot_date"),
        }),
        ("Quantities by Branch", {
            "fields": (
                "qty_alkarimia", "qty_benghazi", "qty_mazraa",
                "qty_dahmani", "qty_janzour", "qty_misrata",
            ),
        }),
        ("Values by Branch (LYD)", {
            "fields": (
                "value_alkarimia", "value_mazraa",
                "value_dahmani", "value_janzour", "value_misrata",
            ),
        }),
        ("Totals", {
            "fields": ("total_qty", "cost_price", "total_value"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
