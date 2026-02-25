from django.contrib import admin
from .models import MaterialMovement


@admin.register(MaterialMovement)
class MaterialMovementAdmin(admin.ModelAdmin):
    list_display = [
        "material_code", "material_name", "movement_type",
        "movement_date", "branch_name", "qty_in", "qty_out",
        "total_in", "total_out", "company",
    ]
    list_filter = ["company", "movement_type", "movement_date"]
    search_fields = [
        "material_code", "material_name", "lab_code",
        "branch_name", "customer_name",
    ]
    readonly_fields = ["id", "created_at"]
    ordering = ["-movement_date", "material_code"]
    list_per_page = 100
    date_hierarchy = "movement_date"

    fieldsets = (
        ("Reference", {
            "fields": ("id", "company", "product", "material_code", "lab_code",
                       "material_name", "category"),
        }),
        ("Movement", {
            "fields": ("movement_date", "movement_type", "movement_type_raw"),
        }),
        ("Quantities In", {
            "fields": ("qty_in", "price_in", "total_in"),
            "classes": ("collapse",),
        }),
        ("Quantities Out", {
            "fields": ("qty_out", "price_out", "total_out"),
            "classes": ("collapse",),
        }),
        ("Balance", {
            "fields": ("balance_price",),
        }),
        ("Branch / Customer", {
            "fields": ("branch", "branch_name", "customer", "customer_name"),
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )
