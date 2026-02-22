from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


# =============================================================================
# JWT / AUTH EXCEPTIONS
# =============================================================================

class TokenExpiredException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Your session has expired. Please log in again."
    default_code = "token_expired"


class TokenBlacklistedException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "This token has been revoked. Please log in again."
    default_code = "token_blacklisted"


class InvalidTokenVersionException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Your session is invalid due to a password change. Please log in again."
    default_code = "token_version_mismatch"


class SuspiciousDeviceException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Unrecognized device. Session invalidated for security reasons."
    default_code = "suspicious_device"


class TokenReuseDetectedException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Suspicious activity detected. All your sessions have been closed for security reasons."
    default_code = "token_reuse_detected"


# =============================================================================
# ACCOUNT EXCEPTIONS
# =============================================================================

class AccountPendingException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your account is pending approval by an administrator."
    default_code = "account_pending"


class AccountRejectedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your access request has been rejected. Contact an administrator."
    default_code = "account_rejected"


class AccountSuspendedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your account has been suspended. Contact an administrator."
    default_code = "account_suspended"


# =============================================================================
# PERMISSION EXCEPTIONS
# =============================================================================

class PermissionDeniedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have the necessary permissions to perform this action."
    default_code = "permission_denied"


class TooManyLoginAttemptsException(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Too many login attempts. Your access is temporarily blocked. Try again in 15 minutes."
    default_code = "rate_limited"


# =============================================================================
# BUSINESS EXCEPTIONS
# =============================================================================

class ResourceNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "The requested resource was not found."
    default_code = "not_found"


class ValidationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The provided data is invalid."
    default_code = "validation_error"


class ConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A conflict exists with existing data."
    default_code = "conflict"


# =============================================================================
# GLOBAL EXCEPTION HANDLER
# =============================================================================

def custom_exception_handler(exc, context):
    """
    Global exception handler for the API.
    Formats all errors consistently.
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
                error_data["message"] = "Validation error."
                error_data["errors"] = response.data
        elif isinstance(response.data, list):
            error_data["message"] = response.data[0] if response.data else "Unknown error."
        else:
            error_data["message"] = str(response.data)

        response.data = error_data

    return response