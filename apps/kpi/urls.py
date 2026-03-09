# apps/kpi/urls.py
from django.urls import path
from .views import CreditKPIView
from .views_sales import SalesKPIView
from .views_stock import StockKPIView
from apps.kpi.views_supply import supply_kpi_view

app_name = "kpi"

urlpatterns = [
    path("credit/", CreditKPIView.as_view(), name="credit-kpis"),
    path("sales/",  SalesKPIView.as_view(),  name="sales-kpis"),   
    path("stock/",  StockKPIView.as_view(),  name="stock-kpis"), 
    path("supply/",  supply_kpi_view,         name="supply-kpis"),
]