import logging
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import ActiveSession, LoginAttempt
from .serializers import (
    ActiveSessionSerializer,
    TokenRefreshInputSerializer,
    RevokeSessionInputSerializer,
)
from .services import TokenService
from .tokens import CustomRefreshToken
from .utils import get_client_ip

security_logger = logging.getLogger("security")


class LoginView(APIView):
    """
    POST /api/auth/login/

    Authentifie un utilisateur et retourne une paire de tokens JWT.

    Corps de la requête :
        - email    : adresse email de l'utilisateur
        - password : mot de passe

    Réponse succès (200) :
        - access     : access token JWT (durée : 60 minutes)
        - refresh    : refresh token JWT (durée : 7 jours)
        - session_id : identifiant de la session créée
        - user       : informations de base de l'utilisateur connecté

    Erreurs possibles :
        - 400 : données manquantes
        - 401 : identifiants incorrects
        - 403 : compte en attente / rejeté / suspendu
        - 429 : trop de tentatives (géré par RateLimitLoginMiddleware)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import get_user_model, authenticate
        User = get_user_model()

        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")

        if not email or not password:
            return Response(
                {"error": "L'email et le mot de passe sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Authentification des identifiants
        user = authenticate(request, username=email, password=password)

        if user is None:
            # Enregistrement de la tentative échouée
            LoginAttempt.objects.create(
                email=email,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                is_successful=False,
                failure_reason="invalid_credentials",
            )
            return Response(
                {"error": "Email ou mot de passe incorrect."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Vérification du statut du compte
        account_status_error = self._check_account_status(user)
        if account_status_error:
            LoginAttempt.objects.create(
                email=email,
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                is_successful=False,
                failure_reason=account_status_error["code"],
            )
            return Response(
                {"error": account_status_error["message"]},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Enregistrement de la tentative réussie
        LoginAttempt.objects.create(
            email=email,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            is_successful=True,
        )

        # Génération des tokens et création de la session
        tokens = TokenService.issue_tokens(user=user, request=request)

        return Response(
            {
                **tokens,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.get_full_name(),
                    "role": user.role,
                    "must_change_password": user.must_change_password,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _check_account_status(self, user) -> dict | None:
        """
        Vérifie que le compte est autorisé à se connecter.

        Returns:
            None si le compte est valide.
            Dict avec "code" et "message" si le compte est bloqué.
        """
        status_messages = {
            "pending": {
                "code": "account_pending",
                "message": "Votre compte est en attente d'approbation par un administrateur.",
            },
            "rejected": {
                "code": "account_rejected",
                "message": "Votre demande d'accès a été rejetée. Contactez un administrateur.",
            },
            "suspended": {
                "code": "account_suspended",
                "message": "Votre compte a été suspendu. Contactez un administrateur.",
            },
        }
        return status_messages.get(user.status)


class RefreshView(APIView):
    """
    POST /api/auth/token/refresh/

    Renouvelle l'access token via rotation du refresh token.
    L'ancien refresh token est immédiatement révoqué et un nouveau est émis.

    Corps de la requête :
        - refresh : refresh token actuel

    Réponse succès (200) :
        - access  : nouvel access token
        - refresh : nouveau refresh token

    Erreurs possibles :
        - 400 : refresh token manquant ou invalide
        - 401 : token expiré, révoqué, ou réutilisé (attaque détectée)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenRefreshInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_refresh_token = serializer.validated_data["refresh"]

        try:
            # Décodage et validation du refresh token
            refresh_token = CustomRefreshToken(raw_refresh_token)
            token_payload = refresh_token.payload

            # Rotation : révoque l'ancien, génère le nouveau
            new_tokens = TokenService.rotate_refresh_token(
                old_refresh_token_payload=token_payload,
                request=request,
            )
            return Response(new_tokens, status=status.HTTP_200_OK)

        except ValueError as e:
            # Réutilisation d'un ancien token détectée : tous les tokens révoqués
            return Response(
                {"error": str(e), "code": "token_reuse_detected"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except TokenError as e:
            raise InvalidToken(e.args[0])


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Déconnecte l'utilisateur de l'appareil actuel uniquement.
    Révoque le refresh token de la session courante.

    Corps de la requête :
        - refresh : refresh token de la session à fermer

    Réponse succès (200) :
        - message : confirmation de déconnexion
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_refresh_token = request.data.get("refresh")

        if not raw_refresh_token:
            return Response(
                {"error": "Le refresh token est requis pour se déconnecter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh_token = CustomRefreshToken(raw_refresh_token)
            token_jti = refresh_token["jti"]

            TokenService.revoke_token(
                token_jti=token_jti,
                user=request.user,
                token_type="refresh",
                reason="logout",
            )

            return Response(
                {"message": "Déconnexion réussie."},
                status=status.HTTP_200_OK,
            )

        except TokenError:
            return Response(
                {"error": "Refresh token invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LogoutAllView(APIView):
    """
    POST /api/auth/logout-all/

    Déconnecte l'utilisateur de TOUS ses appareils simultanément.
    Révoque toutes les sessions actives.

    Aucun corps de requête requis.

    Réponse succès (200) :
        - message          : confirmation
        - sessions_revoked : nombre de sessions révoquées
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = TokenService.revoke_all_user_tokens(
            user=request.user,
            reason="logout_all",
        )

        return Response(
            {
                "message": f"Déconnexion de tous vos appareils réussie.",
                "sessions_revoked": count,
            },
            status=status.HTTP_200_OK,
        )


class ActiveSessionsView(APIView):
    """
    GET /api/auth/sessions/

    Retourne la liste de tous les appareils actuellement connectés
    au compte de l'utilisateur authentifié.

    Réponse succès (200) :
        - sessions : liste des sessions actives avec device_name, ip, last_activity
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = ActiveSession.objects.filter(user=request.user).order_by("-last_activity")
        serializer = ActiveSessionSerializer(sessions, many=True)

        return Response(
            {"sessions": serializer.data},
            status=status.HTTP_200_OK,
        )


class RevokeSessionView(APIView):
    """
    DELETE /api/auth/sessions/{session_id}/

    Révoque une session spécifique à distance (déconnecte un appareil précis).
    L'utilisateur ne peut révoquer que ses propres sessions.

    Paramètre URL :
        - session_id : UUID de la session à révoquer

    Réponse succès (200) :
        - message : confirmation
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        try:
            session = ActiveSession.objects.get(
                id=session_id,
                user=request.user,
            )
        except ActiveSession.DoesNotExist:
            return Response(
                {"error": "Session introuvable ou accès non autorisé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        TokenService.revoke_token(
            token_jti=session.refresh_token_jti,
            user=request.user,
            token_type="refresh",
            reason="admin_revoked",
        )

        return Response(
            {"message": "Session révoquée avec succès."},
            status=status.HTTP_200_OK,
        )
