"""
apps/ai_insights/urls.py
"""
from django.urls import path
from .views import (
    AlertExplainView,
    AlertResolveView,
    AlertResolutionsView,
    ChurnPredictionView,
    HighValueChurnView,
    AIUsageView,
)

app_name = "ai_insights"

urlpatterns = [
    # Alert Explain
    path("alerts/explain/",           AlertExplainView.as_view(),    name="alert-explain"),
    # Alert Resolution
    path("alerts/resolve/",           AlertResolveView.as_view(),    name="alert-resolve"),
    path("alerts/resolve/<str:alert_id>/", AlertResolveView.as_view(), name="alert-resolve-delete"),
    # Alert Resolutions List
    path("alerts/resolutions/",       AlertResolutionsView.as_view(), name="alert-resolutions"),
    # Churn Prediction
    path("churn/",                    ChurnPredictionView.as_view(), name="churn-prediction"),
    path("churn/high-value/",         HighValueChurnView.as_view(),  name="hv-churn"),
    # AI Usage Dashboard
    path("usage/",                    AIUsageView.as_view(),         name="ai-usage"),
]