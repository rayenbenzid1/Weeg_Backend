from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "product_code", "product_name", "category",
        "lab_code", "company", "created_at",
    ]
    list_filter = ["company", "category"]
    search_fields = ["product_code", "product_name", "lab_code"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["category", "product_name"]
    list_per_page = 50

    fieldsets = (
        ("Identity", {
            "fields": ("id", "company", "product_code", "product_name"),
        }),
        ("Details", {
            "fields": ("lab_code", "category"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
