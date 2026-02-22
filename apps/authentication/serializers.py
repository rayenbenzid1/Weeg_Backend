from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.companies.models import Company

User = get_user_model()


# =============================================================================
# SERIALIZERS DE LECTURE (affichage)
# =============================================================================

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Affiche le profil complet de l'utilisateur connecté.
    Utilisé par GET /api/users/profile/
    """
    full_name = serializers.CharField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    company_name = serializers.CharField(read_only=True)

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
            "company",
            "company_name",
            "must_change_password",
            "is_verified",
            "created_at",
        ]
        read_only_fields = [
            "id", "email", "role", "status", "permissions_list",
            "branch", "branch_name", "company", "company_name",
            "full_name", "must_change_password", "is_verified", "created_at",
        ]


class UserListSerializer(serializers.ModelSerializer):
    """
    Affichage simplifié d'un utilisateur dans une liste.
    """
    full_name = serializers.CharField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    company_name = serializers.CharField(read_only=True)

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
            "company",
            "company_name",
            "created_at",
            "permissions_list",
        ]
        read_only_fields = fields


# =============================================================================
# SERIALIZERS D'ÉCRITURE (création / modification)
# =============================================================================

class UpdateProfileSerializer(serializers.ModelSerializer):
    """
    Permet à un utilisateur de mettre à jour son propre profil.
    """
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]

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
    """
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

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
        if data["old_password"] == data["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "Le nouveau mot de passe doit être différent de l'ancien."}
            )
        return data


# =============================================================================
# SERIALIZERS SIGNUP MANAGER
# =============================================================================

class ManagerSignupSerializer(serializers.ModelSerializer):
    """
    Permet à un manager de s'inscrire via le formulaire public.
    Le compte est créé avec le statut PENDING.
    Le champ 'company_name' crée ou réutilise une Company existante.
    """
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, required=True)
    company_name = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Nom officiel de la société du manager.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "company_name",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def validate_company_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Le nom de la société est obligatoire.")
        return name

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
        company_name = validated_data.pop("company_name")

        # Récupère ou crée la société
        company, _ = Company.objects.get_or_create(name=company_name)

        user = User(
            role=User.Role.MANAGER,
            status=User.AccountStatus.PENDING,
            is_verified=False,
            must_change_password=False,
            company=company,
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


# =============================================================================
# SERIALIZERS CRÉATION AGENT PAR MANAGER
# =============================================================================

class CreateAgentSerializer(serializers.ModelSerializer):
    """
    Permet à un manager de créer un compte agent.
    La Company de l'agent est automatiquement celle du Manager — non modifiable.
    """
    temporary_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Mot de passe temporaire pour l'agent.",
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

    def create(self, validated_data):
        temporary_password = validated_data.pop("temporary_password")
        manager = self.context["request"].user

        user = User(
            role=User.Role.AGENT,
            status=User.AccountStatus.ACTIVE,
            is_verified=True,
            must_change_password=True,
            created_by=manager,
            # L'agent hérite automatiquement de la Company de son Manager
            company=manager.company,
            **validated_data,
        )
        user.set_password(temporary_password)
        user.save()
        return user


# =============================================================================
# SERIALIZERS RESET PASSWORD
# =============================================================================

class RequestPasswordResetSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(required=True)

    def validate_user_id(self, value):
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Utilisateur introuvable.")
        return value


class ConfirmPasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

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
    class Meta:
        model = User
        fields = ["permissions_list"]

    def validate_permissions_list(self, value):
        allowed_permissions = {
            "import-data",
            "export-data",
            "view-dashboard",
            "view-reports",
            "generate-reports",
            "view-kpi",
            "filter-dashboard",
            "view-sales",
            "view-inventory",
            "view-customer-payments",
            "view-aging",
            "receive-notifications",
            "manage-alerts",
            "view-profile",
            "change-password",
            "ai-insights",
        }
        invalid = set(value) - allowed_permissions
        if invalid:
            raise serializers.ValidationError(
                f"Permissions invalides : {', '.join(invalid)}."
            )
        return value

class UpdateUserStatusSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(required=False, allow_blank=True)

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
    action = serializers.ChoiceField(choices=["approve", "reject"], required=True)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data["action"] == "reject" and not data.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": "Le motif est obligatoire pour rejeter une demande."}
            )
        return data
