# """
# apps/authentication/signup_views.py

# Vues dédiées au flux d'inscription Manager :
#     - ManagerSignupView          POST /api/auth/signup/
#     - PendingManagersListView    GET  /api/auth/signup/pending/
#     - ApproveRejectManagerView   POST /api/auth/signup/review/<manager_id>/
#     - RequestPasswordResetView   POST /api/auth/password-reset/request/
#     - ConfirmPasswordResetView   POST /api/auth/password-reset/confirm/
# """

# import logging
# # import threading

# from django.contrib.auth import get_user_model
# from rest_framework import status
# from rest_framework.permissions import AllowAny, IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from .serializers import (
#     ManagerSignupSerializer,
#     ApproveRejectManagerSerializer,
#     UserListSerializer,
#     RequestPasswordResetSerializer,
#     ConfirmPasswordResetSerializer,
# )
# from .services import EmailService, UserService

# logger = logging.getLogger("django")
# User = get_user_model()


# # def _send_async(fn, *args, **kwargs):
# #     """Envoi d'email dans un thread daemon pour ne pas bloquer la réponse."""
# #     t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
# #     t.start()


# # =============================================================================
# # SIGNUP MANAGER
# # =============================================================================

# class ManagerSignupView(APIView):
#     """
#     POST /api/auth/signup/

#     Inscription publique d'un Manager.
#     Crée le compte avec statut PENDING puis notifie tous les admins actifs par email.
#     """
#     permission_classes = [AllowAny]

#     def post(self, request):
#         serializer = ManagerSignupSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         manager = serializer.save()

#         # # Envoi email — asynchrone pour ne pas bloquer la réponse HTTP
#         # _send_async(EmailService.send_admin_new_manager_request, manager)

#         # logger.info(
#         #     f"[SIGNUP] Nouveau Manager inscrit : {manager.email} | "
#         #     f"Société : {manager.company_name} | "
#         #     f"Notification admin lancée en arrière-plan."
#         # )
#         try:
#            from .services import EmailService as ES
#            try:
#               ES.send_admin_new_manager_request(manager)            logger.info(
#                 f"[SIGNUP] Manager inscrit : {manager.email} | "
#                 f"Société : {manager.company_name} | Email admin envoyé."
#             )
#         except Exception as e:
#             logger.error(f"[SIGNUP] Email non envoyé pour {manager.email} : {e}")
#         return Response(
#             {
#                 "message": (
#                     "Votre compte a été créé avec succès. "
#                     "Un administrateur va examiner votre demande. "
#                     "Vous recevrez un email dès que votre compte sera activé."
#                 ),
#                 "status": "pending",
#             },
#             status=status.HTTP_201_CREATED,
#         )


# # =============================================================================
# # LISTE DES MANAGERS EN ATTENTE
# # =============================================================================

# class PendingManagersListView(APIView):
#     """
#     GET /api/auth/signup/pending/

#     Retourne tous les managers en attente de validation.
#     Accessible uniquement aux admins.
#     """
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         if not request.user.is_admin:
#             return Response(
#                 {"error": "Accès réservé aux administrateurs."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         pending = (
#             User.objects.filter(
#                 role=User.Role.MANAGER,
#                 status=User.AccountStatus.PENDING,
#             )
#             .select_related("company")
#             .order_by("-created_at")
#         )

#         serializer = UserListSerializer(pending, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)


# # =============================================================================
# # APPROBATION / REJET PAR L'ADMIN
# # =============================================================================

# class ApproveRejectManagerView(APIView):
#     """
#     POST /api/auth/signup/review/<manager_id>/

#     L'Admin approuve ou rejette un Manager en attente.

#     Body :
#         { "action": "approve" | "reject", "reason": "..." }
#     Le motif est obligatoire si action == "reject".
#     """
#     permission_classes = [IsAuthenticated]

#     def post(self, request, manager_id):
#         # Seul l'admin peut approuver / rejeter
#         if not request.user.is_admin:
#             return Response(
#                 {"error": "Accès réservé aux administrateurs."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # Récupération du manager cible
#         try:
#             manager = User.objects.get(id=manager_id, role=User.Role.MANAGER)
#         except User.DoesNotExist:
#             return Response(
#                 {"error": "Manager introuvable."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # Validation du body
#         serializer = ApproveRejectManagerSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         action = serializer.validated_data["action"]
#         reason = serializer.validated_data.get("reason", "")

#         if action == "approve":
#             if manager.status == User.AccountStatus.APPROVED:
#                 return Response(
#                     {"error": "Ce compte est déjà approuvé."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#             # approve() → status=APPROVED, is_verified=True
#             UserService.approve_manager(manager=manager, admin=request.user)

#             logger.info(
#                 f"[APPROVE] Manager {manager.email} approuvé par {request.user.email}."
#             )

#             return Response(
#                 {
#                     "message": (
#                         f"Le compte de {manager.full_name} a été approuvé. "
#                         f"Un email de confirmation lui a été envoyé."
#                     ),
#                     "user": UserListSerializer(manager).data,
#                 },
#                 status=status.HTTP_200_OK,
#             )

#         else:  # reject
#             if manager.status == User.AccountStatus.REJECTED:
#                 return Response(
#                     {"error": "Ce compte a déjà été rejeté."},
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )
#             # reject() → status=REJECTED, rejection_reason=reason
#             UserService.reject_manager(manager=manager, admin=request.user, reason=reason)

#             logger.info(
#                 f"[REJECT] Manager {manager.email} rejeté par {request.user.email}. "
#                 f"Motif : {reason}."
#             )

#             return Response(
#                 {
#                     "message": (
#                         f"La demande de {manager.full_name} a été rejetée. "
#                         f"Un email de notification lui a été envoyé."
#                     ),
#                     "user": UserListSerializer(manager).data,
#                 },
#                 status=status.HTTP_200_OK,
#             )


# # =============================================================================
# # RESET MOT DE PASSE
# # =============================================================================

# class RequestPasswordResetView(APIView):
#     """
#     POST /api/auth/password-reset/request/

#     Demande de réinitialisation de mot de passe.
#     Envoie un lien par email à l'utilisateur concerné.
#     """
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         serializer = RequestPasswordResetSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         target_user = User.objects.get(id=serializer.validated_data["user_id"])

#         # Seul un admin ou le manager responsable peut déclencher un reset
#         if request.user.is_agent:
#             return Response(
#                 {"error": "Vous n'avez pas le droit de réinitialiser ce mot de passe."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         UserService.request_password_reset(
#             target_user=target_user,
#             requesting_user=request.user,
#         )

#         return Response(
#             {"message": f"Un lien de réinitialisation a été envoyé à {target_user.email}."},
#             status=status.HTTP_200_OK,
#         )


# class ConfirmPasswordResetView(APIView):
#     """
#     POST /api/auth/password-reset/confirm/

#     Confirmation de la réinitialisation avec le token temporaire.
#     """
#     permission_classes = [AllowAny]

#     def post(self, request):
#         from apps.token_security.tokens import TemporaryToken
#         from rest_framework_simplejwt.exceptions import TokenError

#         serializer = ConfirmPasswordResetSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             token = TemporaryToken(serializer.validated_data["token"])
#             user_id = token["user_id"]
#             action = token.get("action")
#             if action != "password_reset":
#                 raise TokenError("Token invalide pour cette action.")
#         except TokenError as e:
#             return Response(
#                 {"error": f"Token invalide ou expiré : {str(e)}"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         try:
#             user = User.objects.get(id=user_id)
#         except User.DoesNotExist:
#             return Response(
#                 {"error": "Utilisateur introuvable."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         UserService.reset_password(
#             user=user,
#             new_password=serializer.validated_data["new_password"],
#         )

#         return Response(
#             {"message": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."},
#             status=status.HTTP_200_OK,
#         )


"""
apps/authentication/signup_views.py
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    ManagerSignupSerializer,
    ApproveRejectManagerSerializer,
    UserListSerializer,
    RequestPasswordResetSerializer,
    ConfirmPasswordResetSerializer,
)
from .services import EmailService, UserService

logger = logging.getLogger("django")
User = get_user_model()


class ManagerSignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ManagerSignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        manager = serializer.save()

        EmailService.send_admin_new_manager_request(manager)
        logger.info(f"[SIGNUP] Manager inscrit : {manager.email} | Email admin envoyé.")

        return Response(
            {
                "message": (
                    "Votre compte a été créé avec succès. "
                    "Un administrateur va examiner votre demande. "
                    "Vous recevrez un email dès que votre compte sera activé."
                ),
                "status": "pending",
            },
            status=status.HTTP_201_CREATED,
        )


class PendingManagersListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response(
                {"error": "Accès réservé aux administrateurs."},
                status=status.HTTP_403_FORBIDDEN,
            )

        pending = (
            User.objects.filter(
                role=User.Role.MANAGER,
                status=User.AccountStatus.PENDING,
            )
            .select_related("company")
            .order_by("-created_at")
        )

        serializer = UserListSerializer(pending, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ApproveRejectManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, manager_id):
        if not request.user.is_admin:
            return Response(
                {"error": "Accès réservé aux administrateurs."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            manager = User.objects.get(id=manager_id, role=User.Role.MANAGER)
        except User.DoesNotExist:
            return Response(
                {"error": "Manager introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ApproveRejectManagerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        if action == "approve":
            if manager.status == User.AccountStatus.APPROVED:
                return Response(
                    {"error": "Ce compte est déjà approuvé."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            UserService.approve_manager(manager=manager, admin=request.user)
            return Response(
                {
                    "message": f"Le compte de {manager.full_name} a été approuvé. Un email lui a été envoyé.",
                    "user": UserListSerializer(manager).data,
                },
                status=status.HTTP_200_OK,
            )

        else:
            if manager.status == User.AccountStatus.REJECTED:
                return Response(
                    {"error": "Ce compte a déjà été rejeté."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            UserService.reject_manager(manager=manager, admin=request.user, reason=reason)
            return Response(
                {
                    "message": f"La demande de {manager.full_name} a été rejetée. Un email lui a été envoyé.",
                    "user": UserListSerializer(manager).data,
                },
                status=status.HTTP_200_OK,
            )


class RequestPasswordResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_agent:
            return Response(
                {"error": "Vous n'avez pas le droit de réinitialiser ce mot de passe."},
                status=status.HTTP_403_FORBIDDEN,
            )

        target_user = User.objects.get(id=serializer.validated_data["user_id"])
        UserService.request_password_reset(
            target_user=target_user,
            requesting_user=request.user,
        )

        return Response(
            {"message": f"Un lien de réinitialisation a été envoyé à {target_user.email}."},
            status=status.HTTP_200_OK,
        )


class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        from apps.token_security.tokens import TemporaryToken
        from rest_framework_simplejwt.exceptions import TokenError

        serializer = ConfirmPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = TemporaryToken(serializer.validated_data["token"])
            user_id = token["user_id"]
            if token.get("action") != "password_reset":
                raise TokenError("Token invalide pour cette action.")
        except TokenError as e:
            return Response(
                {"error": f"Token invalide ou expiré : {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        UserService.reset_password(
            user=user,
            new_password=serializer.validated_data["new_password"],
        )

        return Response(
            {"message": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."},
            status=status.HTTP_200_OK,
        )