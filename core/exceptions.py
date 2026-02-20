from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


# =============================================================================
# EXCEPTIONS JWT / AUTH
# =============================================================================

class TokenExpiredException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Votre session a expiré. Veuillez vous reconnecter."
    default_code = "token_expired"


class TokenBlacklistedException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Ce token a été révoqué. Veuillez vous reconnecter."
    default_code = "token_blacklisted"


class InvalidTokenVersionException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Votre session est invalide suite à un changement de mot de passe. Veuillez vous reconnecter."
    default_code = "token_version_mismatch"


class SuspiciousDeviceException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Appareil non reconnu. Session invalidée par mesure de sécurité."
    default_code = "suspicious_device"


class TokenReuseDetectedException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Activité suspecte détectée. Toutes vos sessions ont été fermées par mesure de sécurité."
    default_code = "token_reuse_detected"


# =============================================================================
# EXCEPTIONS COMPTE
# =============================================================================

class AccountPendingException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre compte est en attente d'approbation par un administrateur."
    default_code = "account_pending"


class AccountRejectedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre demande d'accès a été rejetée. Contactez un administrateur."
    default_code = "account_rejected"


class AccountSuspendedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre compte a été suspendu. Contactez un administrateur."
    default_code = "account_suspended"


# =============================================================================
# EXCEPTIONS PERMISSIONS
# =============================================================================

class PermissionDeniedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Vous n'avez pas les permissions nécessaires pour effectuer cette action."
    default_code = "permission_denied"


class TooManyLoginAttemptsException(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Trop de tentatives de connexion. Votre accès est temporairement bloqué. Réessayez dans 15 minutes."
    default_code = "rate_limited"


# =============================================================================
# EXCEPTIONS MÉTIER
# =============================================================================

class ResourceNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La ressource demandée est introuvable."
    default_code = "not_found"


class ValidationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Les données fournies sont invalides."
    default_code = "validation_error"


class ConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Un conflit existe avec les données existantes."
    default_code = "conflict"


# =============================================================================
# HANDLER GLOBAL D'EXCEPTIONS
# =============================================================================

def custom_exception_handler(exc, context):
    """
    Handler global d'exceptions pour l'API.
    Formate toutes les erreurs de manière cohérente.
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "error": True,
            "status_code": response.status_code,
        }

        if isinstance(response.data, dict):
            if "detail" in response.data:
                error_data["message"] = response.data["detail"]
                if hasattr(response.data["detail"], "code"):
                    error_data["code"] = response.data["detail"].code
            else:
                error_data["message"] = "Erreur de validation."
                error_data["errors"] = response.data
        elif isinstance(response.data, list):
            error_data["message"] = response.data[0] if response.data else "Erreur inconnue."
        else:
            error_data["message"] = str(response.data)

        response.data = error_data

    return response