import logging
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from apps.token_security.tokens import TemporaryToken
from apps.token_security.services import TokenService
from core.permissions import IsAdmin, IsAdminOrManager
from .serializers import (
    ManagerSignupSerializer,
    ApproveRejectManagerSerializer,
    RequestPasswordResetSerializer,
    ConfirmPasswordResetSerializer,
    UserListSerializer,
)
from .services import EmailService, UserService

logger = logging.getLogger("django")
User = get_user_model()


class ManagerSignupView(APIView):
    """
    POST /api/auth/signup/

    Formulaire public d'inscription pour les managers.
    Le compte est créé avec le statut PENDING.
    Un email est automatiquement envoyé à tous les admins pour validation.
    Le manager NE peut PAS se connecter tant que l'admin n'a pas approuvé.

    SCRUM-37 : As a Manager, I want to sign up through a form in order to request access.

    Corps de la requête :
        - email, first_name, last_name, phone_number
        - password, password_confirm

    Réponse succès (201) :
        - message : confirmation que la demande a été envoyée
        - email   : email du compte créé (pour confirmation)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ManagerSignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Création du compte avec statut PENDING
        manager = serializer.save()

        # Notification aux admins pour validation
        try:
            EmailService.send_admin_new_manager_request(manager=manager)
        except Exception as e:
            logger.error(
                f"Échec de l'envoi de l'email de notification aux admins "
                f"pour la demande du manager [{manager.email}] : {e}"
            )

        logger.info(
            f"Nouvelle demande d'accès manager créée : [{manager.email}]."
        )

        return Response(
            {
                "message": (
                    "Votre demande d'accès a bien été enregistrée. "
                    "Un administrateur va examiner votre demande et vous recevrez "
                    "une confirmation par email dans les plus brefs délais."
                ),
                "email": manager.email,
            },
            status=status.HTTP_201_CREATED,
        )


class PendingManagersListView(APIView):
    """
    GET /api/auth/signup/pending/

    Retourne la liste de tous les managers en attente d'approbation.
    Accessible uniquement à l'admin.

    SCRUM-38 : As an Admin, I want to verify the email of a registered Manager.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        pending_managers = User.objects.filter(
            role=User.Role.MANAGER,
            status=User.AccountStatus.PENDING,
        ).order_by("created_at")

        serializer = UserListSerializer(pending_managers, many=True)
        return Response(
            {
                "count": pending_managers.count(),
                "pending_managers": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ApproveRejectManagerView(APIView):
    """
    POST /api/auth/signup/review/{manager_id}/

    Permet à l'admin d'approuver ou de rejeter la demande d'un manager en attente.
    Un email est envoyé au manager dans les deux cas.

    SCRUM-38 : As an Admin, I want to verify the email of a registered Manager
               in order to validate their access.

    Accessible uniquement à l'admin.

    Corps de la requête :
        - action : "approve" | "reject"
        - reason : motif du rejet (obligatoire si action = "reject")

    Réponse succès (200) :
        - message : confirmation de l'action effectuée
        - manager : données du manager mis à jour
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, manager_id):
        # Récupération du manager en attente
        try:
            manager = User.objects.get(
                id=manager_id,
                role=User.Role.MANAGER,
                status=User.AccountStatus.PENDING,
            )
        except User.DoesNotExist:
            return Response(
                {"error": "Manager en attente introuvable. "
                          "Il a peut-être déjà été traité ou n'existe pas."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ApproveRejectManagerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        if action == "approve":
            UserService.approve_manager(manager=manager, admin=request.user)
            message = (
                f"Le compte de {manager.full_name} ({manager.email}) "
                f"a été approuvé avec succès. Il peut maintenant se connecter."
            )
        else:
            UserService.reject_manager(
                manager=manager,
                admin=request.user,
                reason=reason,
            )
            message = (
                f"La demande de {manager.full_name} ({manager.email}) "
                f"a été rejetée. Un email d'information lui a été envoyé."
            )

        return Response(
            {
                "message": message,
                "manager": UserListSerializer(manager).data,
            },
            status=status.HTTP_200_OK,
        )


class RequestPasswordResetView(APIView):
    """
    POST /api/auth/password-reset/request/

    Génère un token temporaire et envoie un lien de reset par email à l'utilisateur ciblé.

    Règles d'accès :
        - Admin   : peut resetter le mot de passe de n'importe quel utilisateur
        - Manager : peut resetter uniquement le mot de passe de ses agents
        - Agent   : ne peut pas accéder à cet endpoint

    SCRUM-23 : As a manager, I can reset a user's password.

    Corps de la requête :
        - user_id : UUID de l'utilisateur dont le mot de passe sera resetté

    Réponse succès (200) :
        - message : confirmation que l'email a été envoyé
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_user_id = serializer.validated_data["user_id"]

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Vérification des droits du manager
        if request.user.is_manager:
            is_own_agent = (
                target_user.role == User.Role.AGENT
                and target_user.branch == request.user.branch
            )
            if not is_own_agent:
                return Response(
                    {"error": "Vous pouvez uniquement réinitialiser le mot de passe "
                              "des agents de votre succursale."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Génération du token et envoi de l'email
        UserService.request_password_reset(
            target_user=target_user,
            requesting_user=request.user,
        )

        return Response(
            {
                "message": f"Un lien de réinitialisation a été envoyé à {target_user.email}. "
                           f"Ce lien est valable pendant 1 heure."
            },
            status=status.HTTP_200_OK,
        )


class ConfirmPasswordResetView(APIView):
    """
    POST /api/auth/password-reset/confirm/

    Valide le token temporaire reçu par email et applique le nouveau mot de passe.
    Le token est immédiatement blacklisté après utilisation (usage unique).
    Tous les tokens actifs de l'utilisateur sont révoqués.

    Accessible publiquement (l'utilisateur n'est pas encore connecté).

    Corps de la requête :
        - token              : token temporaire reçu par email
        - new_password       : nouveau mot de passe
        - new_password_confirm : confirmation du nouveau mot de passe

    Réponse succès (200) :
        - message : confirmation du reset
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token = serializer.validated_data["token"]

        # Décodage et validation du token temporaire
        try:
            token = TemporaryToken(raw_token)
        except TokenError:
            return Response(
                {"error": "Le lien de réinitialisation est invalide ou a expiré. "
                          "Demandez un nouveau lien."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérification que le token est bien de type "password_reset"
        if token.get("action") != "password_reset":
            return Response(
                {"error": "Ce token n'est pas valide pour la réinitialisation du mot de passe."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérification que le token n'a pas déjà été utilisé (blacklist)
        from apps.token_security.models import TokenBlacklist
        token_jti = token.get("jti")
        if TokenBlacklist.objects.filter(token_jti=token_jti).exists():
            return Response(
                {"error": "Ce lien de réinitialisation a déjà été utilisé. "
                          "Demandez un nouveau lien."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Récupération de l'utilisateur
        user_id = token.get("user_id")
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Vérification de la version du token (cohérence)
        if int(token.get("token_version", -1)) != user.token_version:
            return Response(
                {"error": "Ce lien de réinitialisation n'est plus valide. "
                          "Demandez un nouveau lien."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Application du nouveau mot de passe
        UserService.reset_password(
            user=user,
            new_password=serializer.validated_data["new_password"],
        )

        # Blackliste du token temporaire (usage unique)
        TokenService.revoke_token(
            token_jti=token_jti,
            user=user,
            token_type="temporary",
            reason="password_reset",
        )

        return Response(
            {
                "message": "Votre mot de passe a été réinitialisé avec succès. "
                           "Vous pouvez maintenant vous connecter avec votre nouveau mot de passe."
            },
            status=status.HTTP_200_OK,
        )
