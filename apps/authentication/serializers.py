from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


# =============================================================================
# SERIALIZERS DE LECTURE (affichage)
# =============================================================================

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Affiche le profil complet de l'utilisateur connecté.
    Utilisé par GET /api/auth/profile/
    """
    full_name = serializers.CharField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "role",
            "status",
            "permissions_list",
            "branch",
            "branch_name",
            "must_change_password",
            "is_verified",
            "created_at",
        ]
        read_only_fields = [
            "id", "email", "role", "status", "permissions_list",
            "branch", "branch_name", "full_name", "must_change_password",
            "is_verified", "created_at",
        ]


class UserListSerializer(serializers.ModelSerializer):
    """
    Affichage simplifié d'un utilisateur dans une liste.
    Utilisé par le manager pour voir la liste de ses agents.
    """
    full_name = serializers.CharField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone_number",
            "role",
            "status",
            "branch_name",
            "created_at",
        ]
        read_only_fields = fields


# =============================================================================
# SERIALIZERS D'ÉCRITURE (création / modification)
# =============================================================================

class UpdateProfileSerializer(serializers.ModelSerializer):
    """
    Permet à un utilisateur de mettre à jour son propre profil.
    Seuls les champs non sensibles sont modifiables.
    Utilisé par PATCH /api/auth/profile/
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
        ]

    def validate_first_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Le prénom ne peut pas être vide.")
        return value.strip()

    def validate_last_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Le nom ne peut pas être vide.")
        return value.strip()


class ChangePasswordSerializer(serializers.Serializer):
    """
    Permet à un utilisateur connecté de changer son propre mot de passe.
    Exige l'ancien mot de passe pour validation.
    Utilisé par POST /api/auth/change-password/

    Après succès :
        - token_version incrémenté → tous les anciens tokens invalidés
        - must_change_password mis à False (pour les agents au premier login)
    """
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Mot de passe actuel de l'utilisateur.",
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Nouveau mot de passe (minimum 8 caractères).",
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirmation du nouveau mot de passe.",
    )

    def validate_new_password(self, value):
        """Applique les validateurs de mot de passe Django (longueur, complexité...)."""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Les deux mots de passe ne correspondent pas."}
            )
        if data["old_password"] == data["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "Le nouveau mot de passe doit être différent de l'ancien."}
            )
        return data


# =============================================================================
# SERIALIZERS SIGNUP MANAGER (SCRUM-37)
# =============================================================================

class ManagerSignupSerializer(serializers.ModelSerializer):
    """
    Permet à un manager de s'inscrire via le formulaire public.
    Le compte est créé avec le statut PENDING.
    Un email est envoyé à l'admin pour approbation.
    Utilisé par POST /api/auth/signup/
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Mot de passe (minimum 8 caractères).",
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirmation du mot de passe.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Les deux mots de passe ne correspondent pas."}
            )
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")

        user = User(
            role=User.Role.MANAGER,
            status=User.AccountStatus.PENDING,
            is_verified=False,
            must_change_password=False,
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


# =============================================================================
# SERIALIZERS CRÉATION AGENT PAR MANAGER (SCRUM-21)
# =============================================================================

class CreateAgentSerializer(serializers.ModelSerializer):
    """
    Permet à un manager de créer un compte agent.
    Le mot de passe initial est temporaire. L'agent devra le changer au premier login.
    Un email avec les identifiants est envoyé automatiquement à l'agent.
    Utilisé par POST /api/auth/agents/
    """
    temporary_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Mot de passe temporaire pour l'agent. Il devra le changer au premier login.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "branch",
            "permissions_list",
            "temporary_password",
        ]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def validate_branch(self, value):
        """
        Vérifie que la succursale appartient bien au manager qui crée l'agent.
        La validation est complétée dans la vue avec le contexte du manager connecté.
        """
        if value is None:
            raise serializers.ValidationError("La succursale est obligatoire pour un agent.")
        return value

    def create(self, validated_data):
        temporary_password = validated_data.pop("temporary_password")
        manager = self.context["request"].user

        user = User(
            role=User.Role.AGENT,
            status=User.AccountStatus.ACTIVE,
            is_verified=True,
            must_change_password=True,
            created_by=manager,
            **validated_data,
        )
        user.set_password(temporary_password)
        user.save()
        return user


# =============================================================================
# SERIALIZERS RESET PASSWORD (SCRUM-23)
# =============================================================================

class RequestPasswordResetSerializer(serializers.Serializer):
    """
    Demande de réinitialisation de mot de passe.
    Utilisé par l'admin ou le manager pour envoyer un lien de reset à un utilisateur.
    Utilisé par POST /api/auth/password-reset/request/
    """
    user_id = serializers.UUIDField(
        required=True,
        help_text="UUID de l'utilisateur dont le mot de passe doit être réinitialisé.",
    )

    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Utilisateur introuvable.")
        return value


class ConfirmPasswordResetSerializer(serializers.Serializer):
    """
    Confirmation de la réinitialisation avec le token temporaire reçu par email.
    Utilisé par POST /api/auth/password-reset/confirm/
    """
    token = serializers.CharField(
        required=True,
        help_text="Token temporaire reçu par email.",
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Nouveau mot de passe.",
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Confirmation du nouveau mot de passe.",
    )

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Les deux mots de passe ne correspondent pas."}
            )
        return data


# =============================================================================
# SERIALIZERS GESTION UTILISATEURS PAR ADMIN/MANAGER
# =============================================================================

class UpdateUserPermissionsSerializer(serializers.ModelSerializer):
    """
    Permet à un admin ou manager de modifier les permissions d'un utilisateur.
    Utilisé par PATCH /api/auth/users/{id}/permissions/
    """

    class Meta:
        model = User
        fields = ["permissions_list"]

    def validate_permissions_list(self, value):
        """Vérifie que les permissions envoyées font partie des permissions autorisées."""
        allowed_permissions = {
            "view-dashboard",
            "view-reports",
            "export-reports",
            "manage-alerts",
            "view-inventory",
            "manage-inventory",
            "view-transactions",
            "manage-transactions",
            "view-customers",
            "manage-customers",
            "view-kpi",
            "import-data",
            "download-templates",
        }
        invalid = set(value) - allowed_permissions
        if invalid:
            raise serializers.ValidationError(
                f"Permissions invalides : {', '.join(invalid)}."
            )
        return value


class UpdateUserStatusSerializer(serializers.ModelSerializer):
    """
    Permet à un admin de suspendre ou réactiver un compte.
    Utilisé par PATCH /api/auth/users/{id}/status/
    """
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Motif de la suspension ou réactivation (optionnel).",
    )

    class Meta:
        model = User
        fields = ["status", "reason"]

    def validate_status(self, value):
        allowed = [User.AccountStatus.ACTIVE, User.AccountStatus.SUSPENDED]
        if value not in allowed:
            raise serializers.ValidationError(
                "Seuls les statuts 'active' et 'suspended' sont modifiables via cet endpoint."
            )
        return value


class ApproveRejectManagerSerializer(serializers.Serializer):
    """
    Permet à l'admin d'approuver ou rejeter la demande d'un manager.
    Utilisé par POST /api/auth/signup/review/{id}/
    """
    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        required=True,
        help_text="'approve' pour approuver, 'reject' pour rejeter.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Motif du rejet (obligatoire si action = 'reject').",
    )

    def validate(self, data):
        if data["action"] == "reject" and not data.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": "Le motif est obligatoire pour rejeter une demande."}
            )
        return data
