from django.contrib import admin
from .models import ImportLog


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = [
        "original_filename", "file_type", "status",
        "success_count", "error_count", "row_count",
        "imported_by", "company", "started_at",
    ]
    list_filter = ["company", "file_type", "status"]
    search_fields = ["original_filename", "imported_by__username"]
    readonly_fields = [
        "id", "company", "imported_by",
        "file_type", "original_filename",
        "status", "row_count", "success_count", "error_count",
        "error_details", "import_context",
        "started_at", "completed_at",
    ]
    ordering = ["-started_at"]
    list_per_page = 50
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False  # ImportLogs are created programmatically only

    def has_change_permission(self, request, obj=None):
        return False  # Read-only in admin

    fieldsets = (
        ("File", {
            "fields": ("id", "company", "imported_by", "file_type", "original_filename"),
        }),
        ("Result", {
            "fields": ("status", "row_count", "success_count", "error_count"),
        }),
        ("Details", {
            "fields": ("error_details", "import_context"),
            "classes": ("collapse",),
        }),
        ("Timing", {
            "fields": ("started_at", "completed_at"),
        }),
    )
