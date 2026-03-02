# apps/kpi/urls.py
from django.urls import path
from .views import CreditKPIView
from .views_sales import SalesKPIView
from .views_stock import StockKPIView

app_name = "kpi"

urlpatterns = [
    path("credit/", CreditKPIView.as_view(), name="credit-kpis"),
    path("sales/",  SalesKPIView.as_view(),  name="sales-kpis"),   
    path("stock/",  StockKPIView.as_view(),  name="stock-kpis"),   
]