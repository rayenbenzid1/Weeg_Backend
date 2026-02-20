from django.urls import path
from .views import (
    ProfileView,
    ChangePasswordView,
    CreateAgentView,
    AgentListView,
    AgentDetailView,
    UpdateUserPermissionsView,
    UpdateUserStatusView,
    AllUsersListView,
    AssignBranchView,
)
from .signup_views import (
    ManagerSignupView,
    PendingManagersListView,
    ApproveRejectManagerView,
    RequestPasswordResetView,
    ConfirmPasswordResetView,
)

app_name = "authentication"

urlpatterns = [
    path("signup/", ManagerSignupView.as_view(), name="manager-signup"),
    path("signup/pending/", PendingManagersListView.as_view(), name="pending-managers"),
    path("signup/review/<uuid:manager_id>/", ApproveRejectManagerView.as_view(), name="review-manager"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("password-reset/request/", RequestPasswordResetView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", ConfirmPasswordResetView.as_view(), name="password-reset-confirm"),
    path("agents/", AgentListView.as_view(), name="agent-list"),
    path("agents/create/", CreateAgentView.as_view(), name="agent-create"),
    path("agents/<uuid:agent_id>/", AgentDetailView.as_view(), name="agent-detail"),
    path("users/", AllUsersListView.as_view(), name="user-list"),
    path("users/<uuid:user_id>/permissions/", UpdateUserPermissionsView.as_view(), name="user-permissions"),
    path("users/<uuid:user_id>/status/", UpdateUserStatusView.as_view(), name="user-status"),
    path("users/<uuid:user_id>/branch/", AssignBranchView.as_view(), name="user-branch"),
]