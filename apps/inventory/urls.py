from django.urls import path
from .views import (
    InventoryListView,
    InventoryDetailView,
    InventoryBranchSummaryView,
    InventorySnapshotDatesView,
    InventoryCategoryBreakdownView,
)

app_name = "inventory"

urlpatterns = [
    # GET /api/inventory/                      → paginated list (filtered by date)
    path("", InventoryListView.as_view(), name="inventory-list"),

    # GET /api/inventory/dates/                → available snapshot dates
    path("dates/", InventorySnapshotDatesView.as_view(), name="inventory-dates"),

    # GET /api/inventory/branch-summary/       → aggregated totals per branch
    path("branch-summary/", InventoryBranchSummaryView.as_view(), name="branch-summary"),

    # GET /api/inventory/category-breakdown/   → totals grouped by product category
    path("category-breakdown/", InventoryCategoryBreakdownView.as_view(), name="category-breakdown"),

    # GET /api/inventory/{id}/                 → full snapshot detail
    path("<uuid:snapshot_id>/", InventoryDetailView.as_view(), name="inventory-detail"),
]
