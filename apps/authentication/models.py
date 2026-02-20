import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """
    Manager custom pour le modèle User.
    Utilise l'email à la place du username.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("status", "active")
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("first_name", "Admin")
        extra_fields.setdefault("last_name", "FASI")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Modèle utilisateur custom qui remplace le User Django par défaut.
    Configuré dans settings/base.py via : AUTH_USER_MODEL = 'authentication.User'

    Trois rôles possibles :
        - admin   : créé manuellement via createsuperuser, gère les managers
        - manager : s'inscrit via formulaire, attend approbation admin, gère les agents
        - agent   : créé par un manager, se connecte directement

    Cycle de vie du statut :
        PENDING  → APPROVED  (admin approuve)
        PENDING  → REJECTED  (admin rejette)
        APPROVED → ACTIVE    (après premier login)
        ACTIVE   → SUSPENDED (admin ou manager suspend)
    """

    # -------------------------------------------------------------------------
    # Manager custom
    # -------------------------------------------------------------------------

    objects = UserManager()

    # -------------------------------------------------------------------------
    # Choix des champs
    # -------------------------------------------------------------------------

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        MANAGER = "manager", "Manager"
        AGENT = "agent", "Agent"

    class AccountStatus(models.TextChoices):
        PENDING = "pending", "En attente d'approbation"
        APPROVED = "approved", "Approuvé"
        REJECTED = "rejected", "Rejeté"
        ACTIVE = "active", "Actif"
        SUSPENDED = "suspended", "Suspendu"

    # -------------------------------------------------------------------------
    # Champs principaux
    # -------------------------------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # On utilise l'email comme identifiant de connexion à la place du username
    email = models.EmailField(
        unique=True,
        verbose_name="Adresse email",
    )

    username = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Nom d'utilisateur",
        help_text="Champ optionnel. L'email est utilisé pour la connexion.",
    )

    first_name = models.CharField(max_length=150, verbose_name="Prénom")
    last_name = models.CharField(max_length=150, verbose_name="Nom")

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Numéro de téléphone",
    )

    # -------------------------------------------------------------------------
    # Rôle et statut
    # -------------------------------------------------------------------------

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.AGENT,
        verbose_name="Rôle",
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
        verbose_name="Statut du compte",
        db_index=True,
    )

    # -------------------------------------------------------------------------
    # Permissions granulaires
    # -------------------------------------------------------------------------

    permissions_list = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Liste des permissions",
        help_text=(
            "Liste des permissions accordées à cet utilisateur. "
            "Stockée dans le payload JWT pour éviter des requêtes DB à chaque appel. "
            "Exemples : ['view-dashboard', 'export-reports', 'manage-alerts']"
        ),
    )

    # -------------------------------------------------------------------------
    # Succursale assignée
    # -------------------------------------------------------------------------

    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Succursale",
        help_text="Succursale assignée à l'utilisateur. Null pour les admins.",
    )

    # -------------------------------------------------------------------------
    # Sécurité JWT avancée
    # -------------------------------------------------------------------------

    token_version = models.PositiveIntegerField(
        default=0,
        verbose_name="Version du token",
        help_text=(
            "Incrémentée à chaque changement ou reset de mot de passe. "
            "Tous les tokens contenant une version inférieure sont automatiquement invalidés."
        ),
    )

    # -------------------------------------------------------------------------
    # Flags spéciaux
    # -------------------------------------------------------------------------

    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Doit changer son mot de passe",
        help_text=(
            "Mis à True lors de la création d'un compte agent par un manager. "
            "L'agent est forcé de changer son mot de passe temporaire au premier login."
        ),
    )

    is_verified = models.BooleanField(
        default=False,
        verbose_name="Email vérifié",
        help_text="True après validation de l'email par l'admin (pour les managers).",
    )

    # -------------------------------------------------------------------------
    # Métadonnées
    # -------------------------------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    # Motif de rejet ou suspension (renseigné par l'admin ou le manager)
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motif de rejet / suspension",
        help_text="Renseigné par l'admin lors du rejet ou de la suspension du compte.",
    )

    # Qui a créé ce compte (manager qui crée un agent, admin qui crée un manager)
    created_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
        verbose_name="Créé par",
    )

    # -------------------------------------------------------------------------
    # Configuration Django Auth
    # -------------------------------------------------------------------------

    # On utilise l'email à la place du username pour la connexion
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "auth_user"
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email}) - {self.role}"

    # -------------------------------------------------------------------------
    # Propriétés utilitaires
    # -------------------------------------------------------------------------

    @property
    def full_name(self) -> str:
        """Retourne le nom complet de l'utilisateur."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER

    @property
    def is_agent(self) -> bool:
        return self.role == self.Role.AGENT

    @property
    def is_active_account(self) -> bool:
        """True si le compte peut se connecter (approuvé ou actif)."""
        return self.status in (self.AccountStatus.APPROVED, self.AccountStatus.ACTIVE)

    # -------------------------------------------------------------------------
    # Méthodes métier
    # -------------------------------------------------------------------------

    def increment_token_version(self) -> None:
        """
        Incrémente la version du token pour invalider tous les tokens existants.
        Appelée lors d'un changement ou reset de mot de passe.
        Sauvegarde uniquement le champ token_version pour performance.
        """
        self.token_version += 1
        self.save(update_fields=["token_version", "updated_at"])

    def approve(self) -> None:
        """
        Approuve le compte d'un manager.
        Appelée par l'admin après vérification de l'email.
        """
        self.status = self.AccountStatus.APPROVED
        self.is_verified = True
        self.save(update_fields=["status", "is_verified", "updated_at"])

    def reject(self, reason: str = "") -> None:
        """
        Rejette la demande d'accès d'un manager.
        Appelée par l'admin.
        """
        self.status = self.AccountStatus.REJECTED
        self.rejection_reason = reason
        self.save(update_fields=["status", "rejection_reason", "updated_at"])

    def suspend(self, reason: str = "") -> None:
        """
        Suspend un compte utilisateur.
        Peut être appelée par l'admin (sur n'importe quel compte)
        ou par un manager (sur les agents de sa succursale uniquement).
        """
        self.status = self.AccountStatus.SUSPENDED
        self.rejection_reason = reason
        self.save(update_fields=["status", "rejection_reason", "updated_at"])

    def activate(self) -> None:
        """
        Active un compte après le premier login réussi.
        Ou réactive un compte suspendu par l'admin.
        """
        self.status = self.AccountStatus.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def has_custom_permission(self, permission: str) -> bool:
        """
        Vérifie si l'utilisateur possède une permission spécifique
        dans sa liste de permissions granulaires.

        Args:
            permission : nom de la permission (ex: 'export-reports')

        Returns:
            True si la permission est accordée.
        """
        return permission in (self.permissions_list or [])