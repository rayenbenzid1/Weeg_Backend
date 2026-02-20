import hashlib
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed
from .models import TokenBlacklist


class TokenVersionValidator:
    """
    Vérifie que la version du token correspond à la version actuelle de l'utilisateur.

    Lors d'un changement de mot de passe ou d'un reset, le champ token_version
    de l'utilisateur est incrémenté en base de données.
    Tout token contenant une ancienne version devient automatiquement invalide,
    sans avoir besoin de les blacklister un par un.
    """

    def validate(self, token_payload: dict, user) -> None:
        """
        Args:
            token_payload : payload décodé du JWT
            user          : instance User récupérée depuis la DB

        Raises:
            AuthenticationFailed si la version du token est obsolète.
        """
        token_version = token_payload.get("token_version")

        if token_version is None:
            raise AuthenticationFailed(
                _("Token invalide : version manquante."),
                code="token_version_missing",
            )

        if int(token_version) != user.token_version:
            raise AuthenticationFailed(
                _("Session expirée. Votre mot de passe a été modifié. Veuillez vous reconnecter."),
                code="token_version_mismatch",
            )


class BlacklistValidator:
    """
    Vérifie que le JTI (JWT ID) du token n'est pas présent dans la blacklist.
    Consulté à chaque requête authentifiée via CustomJWTAuthentication.
    """

    def validate(self, token_jti: str) -> None:
        """
        Args:
            token_jti : identifiant unique du token (champ "jti" du payload)

        Raises:
            AuthenticationFailed si le token a été révoqué.
        """
        if TokenBlacklist.objects.filter(token_jti=token_jti).exists():
            raise AuthenticationFailed(
                _("Token révoqué. Veuillez vous reconnecter."),
                code="token_blacklisted",
            )


class DeviceValidator:
    """
    Vérifie que l'empreinte de l'appareil (device fingerprint) correspond
    à celle enregistrée dans le payload du token lors de la connexion.

    Protège contre le vol de token : même si un attaquant récupère un token,
    il ne peut pas l'utiliser depuis un appareil différent.
    """

    def validate(self, token_payload: dict, current_fingerprint: str) -> None:
        """
        Args:
            token_payload        : payload décodé du JWT
            current_fingerprint  : empreinte de l'appareil de la requête courante

        Raises:
            AuthenticationFailed si l'empreinte ne correspond pas.
        """
        stored_fp = token_payload.get("device_fp")

        if not stored_fp:
            # Token généré sans fingerprint (ancien format) : on tolère
            return

        current_fp_hash = hashlib.sha256(current_fingerprint.encode()).hexdigest()

        if stored_fp != current_fp_hash:
            raise AuthenticationFailed(
                _("Appareil non reconnu. Session invalide."),
                code="device_fingerprint_mismatch",
            )


class IPValidator:
    """
    Vérifie si l'adresse IP de la requête correspond à celle enregistrée lors du login.

    Contrairement au DeviceValidator, ce validateur ne bloque PAS automatiquement
    (les utilisateurs mobiles changent souvent d'IP).
    Il retourne un signal d'avertissement utilisé par SuspiciousActivityMiddleware.
    """

    def validate(self, token_payload: dict, current_ip: str) -> bool:
        """
        Args:
            token_payload : payload décodé du JWT
            current_ip    : adresse IP de la requête courante

        Returns:
            True  : l'IP correspond (situation normale)
            False : l'IP a changé (possible activité suspecte, à logger)
        """
        stored_ip_hash = token_payload.get("ip_hash")

        if not stored_ip_hash:
            return True

        current_ip_hash = hashlib.sha256(current_ip.encode()).hexdigest()
        return stored_ip_hash == current_ip_hash
