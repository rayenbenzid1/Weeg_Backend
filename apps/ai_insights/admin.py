from django.contrib import admin
from django.db.models import Sum, Count
from .models import AlertResolution, AIUsageLog


@admin.register(AlertResolution)
class AlertResolutionAdmin(admin.ModelAdmin):
    list_display  = ["alert_id", "alert_type", "company", "resolved_by", "resolved_at"]
    list_filter   = ["alert_type", "company", "resolved_at"]
    search_fields = ["alert_id", "resolved_by__email", "company__name"]
    readonly_fields = ["id", "resolved_at"]
    ordering      = ["-resolved_at"]
    list_per_page = 50

    def has_add_permission(self, request):
        return False  # Created via API only


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display  = ["created_at", "analyzer", "model", "tokens_used", "cost_usd", "company"]
    list_filter   = ["analyzer", "model", "company", "created_at"]
    readonly_fields = ["id", "created_at"]
    ordering      = ["-created_at"]
    list_per_page = 100

    def has_add_permission(self, request):
        return False  # Created automatically

    def changelist_view(self, request, extra_context=None):
        """Add cost summary to the list view."""
        extra_context = extra_context or {}
        totals = AIUsageLog.objects.aggregate(
            total_tokens=Sum("tokens_used"),
            total_cost=Sum("cost_usd"),
            total_calls=Count("id"),
        )
        extra_context["totals"] = totals
        return super().changelist_view(request, extra_context)