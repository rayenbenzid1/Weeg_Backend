from django.urls import path
from .views import CompanyListView, CompanyDetailView

app_name = "companies"

urlpatterns = [
    path("", CompanyListView.as_view(), name="company-list"),
    path("<uuid:company_id>/", CompanyDetailView.as_view(), name="company-detail"),
]
