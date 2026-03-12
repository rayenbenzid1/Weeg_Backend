from django.urls import path
from .views import (
    BranchListView,
    BranchAliasListView,
    BranchAliasDetailView,
    BranchAliasUnresolvedCountView,
)
app_name = "branches"

urlpatterns = [
    path("", BranchListView.as_view(), name="branch-list"),
     # Aliases
    path("aliases/",                          BranchAliasListView.as_view(),          name="branch-aliases"),
    path("aliases/unresolved-count/",         BranchAliasUnresolvedCountView.as_view(),name="branch-aliases-count"),
    path("aliases/<uuid:alias_id>/",          BranchAliasDetailView.as_view() ),   
]