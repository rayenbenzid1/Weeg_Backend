import logging
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("django")


class BranchFilterMixin:
    """
    Mixin that automatically filters querysets by branch.
    
    - Admin    : sees all branches
    - Manager  : sees only their own branch
    - Agent    : sees only their own branch
    
    To be used in views that return branch-related data.
    """

    def get_branch_queryset(self, queryset):
        user = self.request.user
        if user.role == "admin":
            return queryset
        if user.branch:
            return queryset.filter(branch=user.branch)
        return queryset.none()


class AuditLogMixin:
    """
    Mixin that automatically logs important CRUD actions.
    To be used in sensitive views (create, update, delete).
    """

    def log_action(self, action: str, target: str, details: str = "") -> None:
        user = getattr(self.request, "user", None)
        user_email = user.email if user and user.is_authenticated else "anonymous"
        logger.info(f"[AUDIT] {action} | User: {user_email} | Target: {target} | {details}")


class StandardResponseMixin:
    """
    Mixin to format API responses consistently.
    
    success_response() → 200/201 with message and data
    error_response()   → 4xx with error message
    """

    def success_response(self, data=None, message="Success.", status_code=status.HTTP_200_OK):
        response_data = {"message": message}
        if data is not None:
            response_data["data"] = data
        return Response(response_data, status=status_code)

    def created_response(self, data=None, message="Created successfully."):
        return self.success_response(data=data, message=message, status_code=status.HTTP_201_CREATED)

    def error_response(self, message="An error occurred.", status_code=status.HTTP_400_BAD_REQUEST, errors=None):
        response_data = {"error": message}
        if errors:
            response_data["errors"] = errors
        return Response(response_data, status=status_code)


class PermissionByRoleMixin:
    """
    Mixin to define different permissions based on HTTP method.
    
    Usage in the view:
        permission_classes_by_method = {
            'GET': [IsAuthenticated],
            'POST': [IsAuthenticated, IsAdmin],
            'DELETE': [IsAuthenticated, IsAdmin],
        }
    """
    permission_classes_by_method = {}

    def get_permissions(self):
        method = self.request.method
        if method in self.permission_classes_by_method:
            return [permission() for permission in self.permission_classes_by_method[method]]
        return super().get_permissions()