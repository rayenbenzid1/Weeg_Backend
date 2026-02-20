from django.contrib import admin
from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "email", "is_active", "created_at"]
    list_filter = ["is_active", "city"]
    search_fields = ["name", "city", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]