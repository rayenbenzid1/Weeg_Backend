"""
apps/kpi/urls.py
"""
from django.urls import path
from .views import CreditKPIView

app_name = "kpi"

urlpatterns = [
    # GET /api/kpi/credit/  → All credit/customer KPIs
    path("credit/", CreditKPIView.as_view(), name="credit-kpis"),
]