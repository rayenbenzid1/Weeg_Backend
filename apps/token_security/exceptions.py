from rest_framework.exceptions import APIException
from rest_framework import status


class TokenExpiredException(APIException):
    """
    Levée quand un token JWT a dépassé sa durée de vie.
    Le frontend doit rediriger vers le refresh endpoint ou la page de login.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Votre session a expiré. Veuillez vous reconnecter."
    default_code = "token_expired"


class TokenBlacklistedException(APIException):
    """
    Levée quand un token révoqué est réutilisé après un logout.
    Indique une tentative d'accès avec un token invalide.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Ce token a été révoqué. Veuillez vous reconnecter."
    default_code = "token_blacklisted"


class InvalidTokenVersionException(APIException):
    """
    Levée quand la version du token ne correspond plus à celle de l'utilisateur.
    Déclenché après un changement de mot de passe ou un reset.
    Tous les anciens tokens sont automatiquement invalidés.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Votre session est invalide suite à un changement de mot de passe. Veuillez vous reconnecter."
    default_code = "token_version_mismatch"


class SuspiciousDeviceException(APIException):
    """
    Levée quand l'empreinte de l'appareil (device fingerprint) ne correspond pas
    à celle enregistrée dans le payload du token.
    Possible tentative d'utilisation d'un token volé depuis un autre appareil.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Appareil non reconnu. Session invalidée par mesure de sécurité."
    default_code = "suspicious_device"


class TooManyLoginAttemptsException(APIException):
    """
    Levée par RateLimitLoginMiddleware quand une IP dépasse le nombre
    maximum de tentatives de connexion autorisées.
    """
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Trop de tentatives de connexion. Votre accès est temporairement bloqué. Réessayez dans 15 minutes."
    default_code = "rate_limited"


class AccountPendingException(APIException):
    """
    Levée quand un manager tente de se connecter avant que l'admin
    n'ait approuvé son compte.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre compte est en attente d'approbation par un administrateur."
    default_code = "account_pending"


class AccountRejectedException(APIException):
    """
    Levée quand un manager tente de se connecter après que l'admin
    ait rejeté sa demande d'accès.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre demande d'accès a été rejetée. Contactez un administrateur."
    default_code = "account_rejected"


class AccountSuspendedException(APIException):
    """
    Levée quand un utilisateur tente de se connecter mais que son compte
    a été suspendu manuellement par un admin ou manager.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Votre compte a été suspendu. Contactez un administrateur."
    default_code = "account_suspended"


class PermissionDeniedException(APIException):
    """
    Levée quand un utilisateur tente d'accéder à une ressource
    pour laquelle il n'a pas les permissions nécessaires.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Vous n'avez pas les permissions nécessaires pour effectuer cette action."
    default_code = "permission_denied"


class TokenReuseDetectedException(APIException):
    """
    Levée quand un ancien refresh token (déjà roté) est réutilisé.
    Indique une attaque potentielle. Tous les tokens de l'utilisateur
    sont immédiatement révoqués.
    """
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Activité suspecte détectée. Toutes vos sessions ont été fermées par mesure de sécurité."
    default_code = "token_reuse_detected"
