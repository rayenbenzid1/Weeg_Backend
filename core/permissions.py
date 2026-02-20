from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Accès réservé aux administrateurs uniquement."""
    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsManager(BasePermission):
    """Accès réservé aux managers uniquement."""
    message = "Accès réservé aux managers."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "manager"


class IsAgent(BasePermission):
    """Accès réservé aux agents uniquement."""
    message = "Accès réservé aux agents."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "agent"


class IsAdminOrManager(BasePermission):
    """Accès réservé aux administrateurs et managers."""
    message = "Accès réservé aux administrateurs et managers."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "manager")


class IsAdminOrManagerOrAgent(BasePermission):
    """Accès à tous les rôles authentifiés."""
    message = "Authentification requise."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "manager", "agent")


class IsSameUserOrAdmin(BasePermission):
    """Autorise l'accès si l'utilisateur accède à ses propres données ou si c'est un admin."""
    message = "Vous ne pouvez accéder qu'à vos propres données."

    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated
            and (obj.id == request.user.id or request.user.role == "admin")
        )


class CanManageAgent(BasePermission):
    """Un manager ne peut gérer que les agents de sa propre succursale."""
    message = "Vous ne pouvez gérer que les agents de votre propre succursale."

    def has_object_permission(self, request, view, obj):
        if request.user.role == "admin":
            return True
        if request.user.role == "manager":
            return (
                obj.role == "agent"
                and obj.branch == request.user.branch
            )
        return False


class CanResetPassword(BasePermission):
    """Admin peut resetter n'importe qui. Manager seulement ses agents."""
    message = "Vous n'avez pas le droit de réinitialiser ce mot de passe."

    def has_object_permission(self, request, view, obj):
        if request.user.role == "admin":
            return True
        if request.user.role == "manager":
            return (
                obj.role == "agent"
                and obj.branch == request.user.branch
            )
        return False