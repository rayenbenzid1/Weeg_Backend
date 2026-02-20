from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .validators import TokenVersionValidator, BlacklistValidator, DeviceValidator, IPValidator
from .utils import get_client_ip, get_device_fingerprint


class CustomJWTAuthentication(JWTAuthentication):
    """
    Backend d'authentification JWT personnalisé.
    Remplace le backend par défaut de djangorestframework-simplejwt.

    Vérifie dans l'ordre à chaque requête :
        1. Validité de la signature et de l'expiration (géré par simplejwt)
        2. Présence dans la blacklist
        3. Version du token (invalide si mot de passe changé)
        4. Empreinte de l'appareil (device fingerprint)
        5. Changement d'IP (log uniquement, ne bloque pas)

    À configurer dans settings/base.py :
        REST_FRAMEWORK = {
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "apps.token_security.backends.CustomJWTAuthentication",
            ],
        }
    """

    blacklist_validator = BlacklistValidator()
    version_validator = TokenVersionValidator()
    device_validator = DeviceValidator()
    ip_validator = IPValidator()

    def authenticate(self, request):
        """
        Point d'entrée principal. Appelé par DRF à chaque requête.

        Returns:
            Tuple (user, validated_token) si authentifié avec succès.
            None si aucun token n'est présent (requête anonyme).

        Raises:
            AuthenticationFailed si le token est invalide, révoqué, ou suspect.
        """
        # Récupération du token depuis le header Authorization
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        # Décodage et validation de la signature JWT
        try:
            validated_token = self.get_validated_token(raw_token)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        # Extraction du JTI pour la vérification de blacklist
        token_jti = validated_token.get("jti")
        if not token_jti:
            raise AuthenticationFailed(
                _("Token invalide : JTI manquant."),
                code="token_jti_missing",
            )

        # 1. Vérification blacklist
        self.blacklist_validator.validate(token_jti)

        # Récupération de l'utilisateur depuis la DB
        user = self.get_user(validated_token)

        # 2. Vérification version du token
        self.version_validator.validate(validated_token.payload, user)

        # 3. Vérification empreinte de l'appareil
        device_fingerprint = get_device_fingerprint(request)
        self.device_validator.validate(validated_token.payload, device_fingerprint)

        # 4. Vérification IP (log uniquement si changement détecté)
        current_ip = get_client_ip(request)
        ip_matches = self.ip_validator.validate(validated_token.payload, current_ip)
        if not ip_matches:
            self._log_ip_change(user, current_ip, request)

        return user, validated_token

    def _log_ip_change(self, user, new_ip: str, request) -> None:
        """
        Enregistre un changement d'adresse IP dans les logs de sécurité.
        Ne bloque pas la requête mais permet une surveillance.
        """
        import logging
        security_logger = logging.getLogger("security")
        security_logger.warning(
            f"Changement d'IP détecté pour l'utilisateur [{user.email}]. "
            f"Nouvelle IP : {new_ip}. "
            f"User-Agent : {request.META.get('HTTP_USER_AGENT', 'inconnu')}."
        )
