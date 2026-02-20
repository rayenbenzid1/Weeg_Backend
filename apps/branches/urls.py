from django.urls import path
from .views import BranchListView

app_name = "branches"

urlpatterns = [
    path("", BranchListView.as_view(), name="branch-list"),
]