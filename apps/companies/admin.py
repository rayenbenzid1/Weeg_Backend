from django.contrib import admin
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "industry", "phone", "is_active", "created_at"]
    list_filter = ["is_active", "industry"]
    search_fields = ["name", "phone"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["name"]

    fieldsets = (
        ("Informations principales", {
            "fields": ("id", "name", "industry", "phone", "address")
        }),
        ("Statut", {
            "fields": ("is_active",)
        }),
        ("Métadonnées", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
