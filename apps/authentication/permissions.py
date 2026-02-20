from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

User = get_user_model()


class IsSameUserOrAdmin(BasePermission):
    """
    Autorise l'accès si l'utilisateur accède à ses propres données
    ou si c'est un administrateur.

    Utilisé pour les endpoints de profil détaillé.
    """
    message = "Vous ne pouvez accéder qu'à vos propres données."

    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated
            and (obj.id == request.user.id or request.user.role == User.Role.ADMIN)
        )


class CanManageAgent(BasePermission):
    """
    Vérifie qu'un manager a le droit de gérer un agent spécifique.
    Le manager ne peut gérer que les agents de sa propre succursale.

    Utilisé par AgentDetailView.
    """
    message = "Vous ne pouvez gérer que les agents de votre propre succursale."

    def has_object_permission(self, request, view, obj):
        if request.user.role == User.Role.ADMIN:
            return True

        if request.user.role == User.Role.MANAGER:
            return (
                obj.role == User.Role.AGENT
                and obj.branch == request.user.branch
            )

        return False


class CanResetPassword(BasePermission):
    """
    Vérifie qu'un utilisateur a le droit de réinitialiser le mot de passe
    d'un autre utilisateur.

    Règles :
        - Admin   : peut resetter n'importe qui
        - Manager : peut resetter uniquement ses agents
        - Agent   : ne peut pas resetter le mot de passe de quelqu'un d'autre
    """
    message = "Vous n'avez pas le droit de réinitialiser ce mot de passe."

    def has_object_permission(self, request, view, obj):
        if request.user.role == User.Role.ADMIN:
            return True

        if request.user.role == User.Role.MANAGER:
            return (
                obj.role == User.Role.AGENT
                and obj.branch == request.user.branch
            )

        return False
