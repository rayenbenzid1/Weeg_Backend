from django.urls import path
from .views import (
    TransactionListView,
    TransactionDetailView,
    TransactionSummaryView,
    TransactionTypeBreakdownView,
    TransactionBranchBreakdownView,
)

app_name = "transactions"

urlpatterns = [
    # GET /api/transactions/                    → paginated list + filters
    path("", TransactionListView.as_view(), name="transaction-list"),

    # GET /api/transactions/summary/            → monthly sales vs purchases
    path("summary/", TransactionSummaryView.as_view(), name="transaction-summary"),

    # GET /api/transactions/type-breakdown/     → totals grouped by movement type
    path("type-breakdown/", TransactionTypeBreakdownView.as_view(), name="type-breakdown"),

    # GET /api/transactions/branch-breakdown/   → sales totals grouped by branch
    path("branch-breakdown/", TransactionBranchBreakdownView.as_view(), name="branch-breakdown"),

    # GET /api/transactions/{id}/               → full movement detail
    path("<uuid:movement_id>/", TransactionDetailView.as_view(), name="transaction-detail"),
]
