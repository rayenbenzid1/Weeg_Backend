from rest_framework import serializers
from .models import ActiveSession, LoginAttempt


class ActiveSessionSerializer(serializers.ModelSerializer):
    """
    Sérialise une session active pour affichage dans la liste des appareils connectés.
    Utilisé par ActiveSessionsView et RevokeSessionView.
    """

    class Meta:
        model = ActiveSession
        fields = [
            "id",
            "device_name",
            "ip_address",
            "last_activity",
            "created_at",
            "is_current",
        ]
        read_only_fields = fields


class LoginAttemptSerializer(serializers.ModelSerializer):
    """
    Sérialise une tentative de connexion pour affichage dans l'admin.
    Lecture seule, utilisé uniquement pour consultation.
    """

    class Meta:
        model = LoginAttempt
        fields = [
            "id",
            "email",
            "ip_address",
            "is_successful",
            "failure_reason",
            "attempted_at",
        ]
        read_only_fields = fields


class TokenRefreshInputSerializer(serializers.Serializer):
    """
    Valide le corps de la requête de rotation du refresh token.
    """
    refresh = serializers.CharField(
        required=True,
        help_text="Refresh token JWT à renouveler.",
    )


class RevokeSessionInputSerializer(serializers.Serializer):
    """
    Valide le corps de la requête de révocation d'une session à distance.
    """
    session_id = serializers.UUIDField(
        required=True,
        help_text="UUID de la session active à révoquer.",
    )
