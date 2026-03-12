from django.contrib import admin
from .models import Branch ,BranchAlias


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "email", "is_active", "created_at"]
    list_filter = ["is_active", "city"]
    search_fields = ["name", "city", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]
@admin.register(BranchAlias)
class BranchAliasAdmin(admin.ModelAdmin):
    list_display   = ["alias", "branch", "company", "auto_matched", "created_at"]
    list_filter    = ["auto_matched", "company"]
    search_fields  = ["alias", "branch__name"]
    autocomplete_fields = ["branch"]
    readonly_fields     = ["id", "created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("branch", "company")