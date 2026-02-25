from django.urls import path
from .views import (
    CustomerListView,
    CustomerDetailView,
    CustomerMovementsView,
    CustomerAgingView,
)

app_name = "customers"

urlpatterns = [
    # GET /api/customers/              → paginated list + filters
    # POST /api/customers/             → create (manager/admin)
    path("", CustomerListView.as_view(), name="customer-list"),

    # GET /api/customers/{id}/         → full profile with stats
    # PATCH /api/customers/{id}/       → partial update
    # DELETE /api/customers/{id}/      → hard delete (admin only)
    path("<uuid:customer_id>/", CustomerDetailView.as_view(), name="customer-detail"),

    # GET /api/customers/{id}/movements/   → movement history
    path("<uuid:customer_id>/movements/", CustomerMovementsView.as_view(), name="customer-movements"),

    # GET /api/customers/{id}/aging/       → aging records
    path("<uuid:customer_id>/aging/", CustomerAgingView.as_view(), name="customer-aging"),
]
