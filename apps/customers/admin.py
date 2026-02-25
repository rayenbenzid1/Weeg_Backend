from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        "customer_name", "account_code", "company",
        "phone", "email", "area_code", "created_at",
    ]
    list_filter = ["company"]
    search_fields = ["customer_name", "account_code", "phone", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["customer_name"]
    list_per_page = 50

    fieldsets = (
        ("Identity", {
            "fields": ("id", "company", "customer_name", "account_code"),
        }),
        ("Contact", {
            "fields": ("address", "area_code", "phone", "email"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
