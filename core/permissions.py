from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Access restricted to administrators only."""
    message = "Access restricted to administrators."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsManager(BasePermission):
    """Access restricted to managers only."""
    message = "Access restricted to managers."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "manager"


class IsAgent(BasePermission):
    """Access restricted to agents only."""
    message = "Access restricted to agents."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "agent"


class IsAdminOrManager(BasePermission):
    """Access restricted to administrators and managers."""
    message = "Access restricted to administrators and managers."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "manager")


class IsAdminOrManagerOrAgent(BasePermission):
    """Access granted to all authenticated roles."""
    message = "Authentication required."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("admin", "manager", "agent")


class IsSameUserOrAdmin(BasePermission):
    """Allows access if the user is accessing their own data or if they are an admin."""
    message = "You can only access your own data."

    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated
            and (obj.id == request.user.id or request.user.role == "admin")
        )


class CanManageAgent(BasePermission):
    """A manager can only manage agents from their own branch."""
    message = "You can only manage agents from your own branch."

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
    """Admins can reset anyone's password. Managers can only reset their own agents."""
    message = "You do not have permission to reset this password."

    def has_object_permission(self, request, view, obj):
        if request.user.role == "admin":
            return True
        if request.user.role == "manager":
            return (
                obj.role == "agent"
                and obj.branch == request.user.branch
            )
        return False