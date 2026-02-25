from django.urls import path
from .views import (
    ProductListView,
    ProductDetailView,
    ProductCategoryListView,
    ProductInventoryHistoryView,
    ProductMovementsView,
)

app_name = "products"

urlpatterns = [
    # GET /api/products/              → paginated list + filters
    # POST /api/products/             → create (admin/manager)
    path("", ProductListView.as_view(), name="product-list"),

    # GET /api/products/categories/   → distinct category list (for dropdowns)
    path("categories/", ProductCategoryListView.as_view(), name="product-categories"),

    # GET /api/products/{id}/         → full detail with stats
    # PATCH /api/products/{id}/       → partial update
    # DELETE /api/products/{id}/      → hard delete (admin only)
    path("<uuid:product_id>/", ProductDetailView.as_view(), name="product-detail"),

    # GET /api/products/{id}/inventory/   → inventory snapshot history
    path("<uuid:product_id>/inventory/", ProductInventoryHistoryView.as_view(), name="product-inventory"),

    # GET /api/products/{id}/movements/   → movement history
    path("<uuid:product_id>/movements/", ProductMovementsView.as_view(), name="product-movements"),
]
