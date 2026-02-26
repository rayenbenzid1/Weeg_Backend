from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        "name", "account_code", "company",
        "phone", "email", "area_code", "is_active", "created_at",
    ]
    list_filter = ["company", "is_active"]
    search_fields = ["name", "account_code", "phone", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["name"]
    list_per_page = 50

    fieldsets = (
        ("Identity", {
            "fields": ("id", "company", "name", "account_code"),
        }),
        ("Contact", {
            "fields": ("address", "area_code", "phone", "email"),
        }),
        ("Status", {
            "fields": ("is_active",),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )