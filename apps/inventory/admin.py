from django.contrib import admin
from .models import InventorySnapshot, InventorySnapshotLine


class InventorySnapshotLineInline(admin.TabularInline):
    model = InventorySnapshotLine
    extra = 0
    readonly_fields = [
        "id", "product_category", "product_code", "product_name",
        "branch_name", "quantity", "unit_cost", "line_value",
    ]
    can_delete = False
    max_num = 0


@admin.register(InventorySnapshot)
class InventorySnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "company_name", "label", "source_file", "fiscal_year",
        "snapshot_date", "uploaded_at", "uploaded_by",
    ]
    list_filter = ["company_name", "fiscal_year", "uploaded_at"]
    search_fields = ["company_name", "label", "source_file"]
    readonly_fields = ["id", "uploaded_at"]
    ordering = ["-uploaded_at"]
    list_per_page = 30
    inlines = [InventorySnapshotLineInline]

    fieldsets = (
        ("Session", {
            "fields": ("id", "company_name", "label", "source_file"),
        }),
        ("Period", {
            "fields": ("snapshot_date", "fiscal_year"),
        }),
        ("Meta", {
            "fields": ("notes", "uploaded_at", "uploaded_by"),
        }),
    )


@admin.register(InventorySnapshotLine)
class InventorySnapshotLineAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot", "product_code", "product_name",
        "branch_name", "quantity", "unit_cost", "line_value",
    ]
    list_filter = ["branch_name", "snapshot__company_name"]
    search_fields = ["product_code", "product_name", "branch_name"]
    readonly_fields = ["id"]
    ordering = ["snapshot", "product_code", "branch_name"]
    list_per_page = 100
