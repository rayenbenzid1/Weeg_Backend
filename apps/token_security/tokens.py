import hashlib
from datetime import timedelta
from django.conf import settings
from rest_framework_simplejwt.tokens import Token, AccessToken, RefreshToken


class CustomAccessToken(AccessToken):
    """
    Access token enrichi avec des informations supplémentaires dans le payload.
    Ces informations permettent d'éviter des requêtes DB supplémentaires
    à chaque vérification de permission.

    Payload enrichi :
        - user_id       : identifiant unique de l'utilisateur
        - role          : admin | manager | agent
        - permissions   : liste des permissions accordées
        - branch_id     : identifiant de la succursale assignée
        - token_version : version pour invalider tous les tokens après changement de mot de passe
        - device_fp     : hash de l'empreinte de l'appareil
        - ip_hash       : hash de l'adresse IP de connexion
    """
    token_type = "access"
    lifetime = timedelta(minutes=60)

    @classmethod
    def for_user_with_context(cls, user, device_fingerprint: str, ip_address: str):
        """
        Génère un access token enrichi pour l'utilisateur donné.
        Doit être appelé uniquement via TokenService.issue_tokens().
        """
        token = cls.for_user(user)

        # Informations de rôle et permissions
        token["role"] = user.role
        token["permissions"] = user.permissions_list
        token["token_version"] = user.token_version

        # Informations de succursale (None si admin sans branche assignée)
        token["branch_id"] = str(user.branch_id) if user.branch_id else None

        # Empreinte de sécurité (hashée pour ne pas exposer les données brutes)
        token["device_fp"] = cls._hash_value(device_fingerprint)
        token["ip_hash"] = cls._hash_value(ip_address)

        return token

    @staticmethod
    def _hash_value(value: str) -> str:
        """Hache une valeur avec SHA-256 pour stockage sécurisé dans le payload."""
        return hashlib.sha256(value.encode()).hexdigest()


class CustomRefreshToken(RefreshToken):
    """
    Refresh token avec support de la rotation automatique.
    À chaque utilisation, l'ancien token est révoqué et un nouveau est généré.
    La détection de réutilisation d'un ancien refresh token déclenche
    la révocation de TOUS les tokens de l'utilisateur (token reuse attack).
    """
    token_type = "refresh"
    lifetime = timedelta(days=7)
    access_token_class = CustomAccessToken

    @classmethod
    def for_user_with_context(cls, user, device_fingerprint: str, ip_address: str):
        """
        Génère un refresh token lié au contexte de connexion.
        Le device_fingerprint et l'ip_address sont stockés pour validation ultérieure.
        """
        token = cls.for_user(user)
        token["device_fp"] = CustomAccessToken._hash_value(device_fingerprint)
        token["ip_hash"] = CustomAccessToken._hash_value(ip_address)
        token["token_version"] = user.token_version
        return token


class TemporaryToken(Token):
    """
    Token à usage unique et courte durée de vie.
    Utilisé exclusivement pour :
        - La réinitialisation de mot de passe (reset password)
        - La vérification d'email lors de l'inscription manager

    Ce token n'est PAS utilisé pour l'authentification des requêtes API.
    Il est transmis via un lien dans un email.
    Une fois utilisé, il est immédiatement blacklisté.
    """
    token_type = "temporary"
    lifetime = timedelta(hours=1)

    @classmethod
    def for_user_action(cls, user, action: str):
        """
        Génère un token temporaire pour une action spécifique.

        Args:
            user    : l'utilisateur concerné
            action  : "password_reset" | "email_verification"

        Returns:
            TemporaryToken avec le contexte de l'action encodé dans le payload.
        """
        token = cls()
        token["user_id"] = str(user.id)
        token["email"] = user.email
        token["action"] = action
        token["token_version"] = user.token_version
        return token
