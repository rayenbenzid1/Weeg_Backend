import uuid
from django.db import models
from django.conf import settings


class RefreshTokenRotation(models.Model):
    """
    Enregistre chaque rotation de refresh token.
    Permet de détecter la réutilisation d'un ancien refresh token (token reuse attack).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_token_rotations",
    )
    old_token_jti = models.CharField(
        max_length=255,
        unique=True,
        help_text="JTI (JWT ID) de l'ancien refresh token révoqué lors de la rotation.",
    )
    new_token_jti = models.CharField(
        max_length=255,
        help_text="JTI du nouveau refresh token généré après rotation.",
    )
    rotated_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "token_refresh_rotation"
        ordering = ["-rotated_at"]
        verbose_name = "Rotation Refresh Token"
        verbose_name_plural = "Rotations Refresh Tokens"

    def __str__(self):
        return f"Rotation [{self.user.email}] à {self.rotated_at}"


class TokenBlacklist(models.Model):
    """
    Stocke les tokens révoqués (logout, logout-all, changement de mot de passe).
    Vérifié à chaque requête via CustomJWTAuthentication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="JWT ID unique du token révoqué.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blacklisted_tokens",
    )
    token_type = models.CharField(
        max_length=20,
        choices=[
            ("access", "Access Token"),
            ("refresh", "Refresh Token"),
            ("temporary", "Temporary Token"),
        ],
        default="refresh",
    )
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Date d'expiration du token. Utilisé pour le nettoyage automatique via Celery.",
    )
    reason = models.CharField(
        max_length=100,
        choices=[
            ("logout", "Déconnexion"),
            ("logout_all", "Déconnexion de tous les appareils"),
            ("password_changed", "Changement de mot de passe"),
            ("password_reset", "Réinitialisation de mot de passe"),
            ("admin_revoked", "Révocation par l'administrateur"),
            ("suspicious_activity", "Activité suspecte détectée"),
            ("token_reuse", "Réutilisation d'un ancien token"),
        ],
        default="logout",
    )

    class Meta:
        db_table = "token_blacklist"
        ordering = ["-revoked_at"]
        verbose_name = "Token Blacklisté"
        verbose_name_plural = "Tokens Blacklistés"

    def __str__(self):
        return f"Blacklist [{self.token_type}] {self.user.email} - {self.reason}"


class ActiveSession(models.Model):
    """
    Représente une session active : un utilisateur connecté sur un appareil précis.
    Créée au login, supprimée au logout.
    Permet à l'utilisateur de voir et révoquer ses sessions à distance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_sessions",
    )
    refresh_token_jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="JTI du refresh token lié à cette session.",
    )
    device_fingerprint = models.CharField(
        max_length=255,
        help_text="Empreinte hashée de l'appareil (User-Agent + autres données).",
    )
    device_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Nom lisible de l'appareil (ex: Chrome sur Windows).",
    )
    ip_address = models.GenericIPAddressField(
        help_text="Adresse IP lors de la connexion.",
    )
    last_activity = models.DateTimeField(
        auto_now=True,
        help_text="Dernière activité détectée sur cette session.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(
        default=False,
        help_text="Indique si c'est la session active de la requête courante.",
    )

    class Meta:
        db_table = "token_active_session"
        ordering = ["-last_activity"]
        verbose_name = "Session Active"
        verbose_name_plural = "Sessions Actives"

    def __str__(self):
        return f"Session [{self.user.email}] - {self.device_name or self.ip_address}"


class LoginAttempt(models.Model):
    """
    Historique de toutes les tentatives de connexion (réussies ou échouées).
    Utilisé par RateLimitLoginMiddleware pour bloquer les attaques par force brute.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(
        db_index=True,
        help_text="Email utilisé lors de la tentative (même si l'utilisateur n'existe pas).",
    )
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(null=True, blank=True)
    is_successful = models.BooleanField(default=False)
    failure_reason = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        choices=[
            ("invalid_credentials", "Identifiants incorrects"),
            ("account_pending", "Compte en attente d'approbation"),
            ("account_rejected", "Compte rejeté"),
            ("account_suspended", "Compte suspendu"),
            ("rate_limited", "Trop de tentatives"),
        ],
    )
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "token_login_attempt"
        ordering = ["-attempted_at"]
        verbose_name = "Tentative de Connexion"
        verbose_name_plural = "Tentatives de Connexion"

    def __str__(self):
        status = "Succès" if self.is_successful else f"Échec ({self.failure_reason})"
        return f"[{status}] {self.email} depuis {self.ip_address}"
