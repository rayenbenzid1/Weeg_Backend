from django.urls import path
from .views import (
    LoginView,
    RefreshView,
    LogoutView,
    LogoutAllView,
    ActiveSessionsView,
    RevokeSessionView,
)

app_name = "token_security"

urlpatterns = [
    # Authentification
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", RefreshView.as_view(), name="token-refresh"),

    # Déconnexion
    path("logout/", LogoutView.as_view(), name="logout"),
    path("logout-all/", LogoutAllView.as_view(), name="logout-all"),

    # Gestion des sessions actives
    path("sessions/", ActiveSessionsView.as_view(), name="active-sessions"),
    path("sessions/<uuid:session_id>/", RevokeSessionView.as_view(), name="revoke-session"),
]
