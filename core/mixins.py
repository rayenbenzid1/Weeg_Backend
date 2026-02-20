import logging
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("django")


class BranchFilterMixin:
    """
    Mixin qui filtre automatiquement les querysets par succursale.
    
    - Admin    : voit toutes les succursales
    - Manager  : voit uniquement sa succursale
    - Agent    : voit uniquement sa succursale
    
    À utiliser dans les vues qui retournent des données liées à une succursale.
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
    Mixin qui log automatiquement les actions CRUD importantes.
    À utiliser dans les vues sensibles (création, modification, suppression).
    """

    def log_action(self, action: str, target: str, details: str = "") -> None:
        user = getattr(self.request, "user", None)
        user_email = user.email if user and user.is_authenticated else "anonyme"
        logger.info(f"[AUDIT] {action} | User: {user_email} | Target: {target} | {details}")


class StandardResponseMixin:
    """
    Mixin pour formater les réponses API de manière cohérente.
    
    success_response() → 200/201 avec message et data
    error_response()   → 4xx avec message d'erreur
    """

    def success_response(self, data=None, message="Succès.", status_code=status.HTTP_200_OK):
        response_data = {"message": message}
        if data is not None:
            response_data["data"] = data
        return Response(response_data, status=status_code)

    def created_response(self, data=None, message="Créé avec succès."):
        return self.success_response(data=data, message=message, status_code=status.HTTP_201_CREATED)

    def error_response(self, message="Une erreur est survenue.", status_code=status.HTTP_400_BAD_REQUEST, errors=None):
        response_data = {"error": message}
        if errors:
            response_data["errors"] = errors
        return Response(response_data, status=status_code)


class PermissionByRoleMixin:
    """
    Mixin pour définir des permissions différentes selon la méthode HTTP.
    
    Utilisation dans la vue :
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