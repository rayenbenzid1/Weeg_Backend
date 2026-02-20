import logging
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin, IsManager, IsAdminOrManager
from .serializers import (
    UserProfileSerializer,
    UserListSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
    CreateAgentSerializer,
    UpdateUserPermissionsSerializer,
    UpdateUserStatusSerializer,
)
from .services import UserService

logger = logging.getLogger("django")
User = get_user_model()


class ProfileView(APIView):
    """
    GET  /api/auth/profile/  → Affiche le profil de l'utilisateur connecté
    PATCH /api/auth/profile/ → Met à jour les informations du profil

    Accessible à tous les rôles (admin, manager, agent).
    Seuls les champs non sensibles sont modifiables (prénom, nom, téléphone).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            {
                "message": "Profil mis à jour avec succès.",
                "user": UserProfileSerializer(request.user).data,
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/

    Permet à un utilisateur connecté de changer son propre mot de passe.
    Exige l'ancien mot de passe pour validation.

    Après succès :
        - token_version incrémenté → tous les anciens tokens invalides
        - must_change_password mis à False (pour les agents au premier login)
        - Email de confirmation envoyé
        - Toutes les sessions révoquées (l'utilisateur doit se reconnecter)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Vérification de l'ancien mot de passe
        if not request.user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"error": "L'ancien mot de passe est incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserService.change_password(
            user=request.user,
            new_password=serializer.validated_data["new_password"],
            request=request,
        )

        return Response(
            {
                "message": "Mot de passe modifié avec succès. "
                           "Toutes vos sessions ont été fermées. Veuillez vous reconnecter."
            },
            status=status.HTTP_200_OK,
        )


class CreateAgentView(APIView):
    """
    POST /api/auth/agents/

    Permet à un manager de créer un compte agent.
    Le manager ne peut créer des agents que pour sa propre succursale.

    Corps de la requête :
        - email, first_name, last_name, phone_number
        - branch : UUID de la succursale (doit être celle du manager)
        - permissions_list : liste des permissions à accorder
        - temporary_password : mot de passe temporaire

    Après succès :
        - Compte agent créé avec must_change_password = True
        - Email avec les identifiants envoyé à l'agent
    """
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request):
        serializer = CreateAgentSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Vérification que la succursale appartient au manager connecté
        branch = serializer.validated_data.get("branch")
        if branch and request.user.branch and branch.id != request.user.branch.id:
            return Response(
                {"error": "Vous ne pouvez créer des agents que pour votre propre succursale."},
                status=status.HTTP_403_FORBIDDEN,
            )

        temporary_password = request.data.get("temporary_password")
        agent = UserService.create_agent(
            validated_data=serializer.validated_data,
            manager=request.user,
            temporary_password=temporary_password,
        )

        return Response(
            {
                "message": f"Compte agent créé avec succès. "
                           f"Les identifiants ont été envoyés à {agent.email}.",
                "agent": UserListSerializer(agent).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentListView(APIView):
    """
    GET /api/users/agents/

    ✅ Manager → voit uniquement les agents de SA succursale.
    ✅ Admin   → voit TOUS les agents de toutes les succursales.
    ❌ Agent   → 403 Forbidden.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    def get(self, request):
        if request.user.is_admin:
            # L'admin voit tous les agents de toutes les succursales
            agents = User.objects.filter(
                role=User.Role.AGENT,
            ).order_by("-created_at")
        else:
            # Le manager voit uniquement les agents de sa succursale
            agents = User.objects.filter(
                role=User.Role.AGENT,
                branch=request.user.branch,
            ).order_by("-created_at")

        serializer = UserListSerializer(agents, many=True)
        return Response(
            {
                "count": agents.count(),
                "agents": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

class AgentDetailView(APIView):
    """
    GET    /api/auth/agents/{id}/  → Détail d'un agent
    PATCH  /api/auth/agents/{id}/  → Mise à jour d'un agent (manager uniquement)
    DELETE /api/auth/agents/{id}/  → Suppression d'un agent (SCRUM-43)

    Le manager ne peut accéder qu'aux agents de sa propre succursale.
    """
    permission_classes = [IsAuthenticated, IsManager]

    def _get_agent(self, agent_id, manager):
        """Récupère l'agent en vérifiant qu'il appartient à la succursale du manager."""
        try:
            return User.objects.get(
                id=agent_id,
                role=User.Role.AGENT,
                branch=manager.branch,
            )
        except User.DoesNotExist:
            return None

    def get(self, request, agent_id):
        agent = self._get_agent(agent_id, request.user)
        if not agent:
            return Response(
                {"error": "Agent introuvable ou accès non autorisé."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserListSerializer(agent)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, agent_id):
        agent = self._get_agent(agent_id, request.user)
        if not agent:
            return Response(
                {"error": "Agent introuvable ou accès non autorisé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UpdateProfileSerializer(agent, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            {
                "message": "Profil de l'agent mis à jour avec succès.",
                "agent": UserListSerializer(agent).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, agent_id):
        """
        Suppression d'un compte agent (SCRUM-43).
        Révoque toutes ses sessions avant suppression.
        """
        from apps.token_security.services import TokenService

        agent = self._get_agent(agent_id, request.user)
        if not agent:
            return Response(
                {"error": "Agent introuvable ou accès non autorisé."},
                status=status.HTTP_404_NOT_FOUND,
            )

        agent_email = agent.email
        TokenService.revoke_all_user_tokens(user=agent, reason="admin_revoked")
        agent.delete()

        logger.info(
            f"Agent [{agent_email}] supprimé par le manager [{request.user.email}]."
        )

        return Response(
            {"message": f"Le compte de {agent_email} a été supprimé avec succès."},
            status=status.HTTP_200_OK,
        )


class UpdateUserPermissionsView(APIView):
    """
    PATCH /api/users/users/{id}/permissions/

    Règles d'accès :
        ✅ Manager → peut modifier les permissions de SES agents uniquement.
        ❌ Admin   → N'a PAS le droit de modifier les permissions des agents.
        ❌ Agent   → Accès refusé (IsAdminOrManager bloque).

    Pour voir les agents, l'admin utilise GET /api/users/users/?role=agent.
    (SCRUM-20)
    """
    # ✅ Garde IsAdminOrManager pour bloquer les agents (403)
    # ❌ Mais on ajoute une vérification explicite : l'admin ne peut PAS modifier les agents
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    def patch(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ✅ MODIFICATION : L'admin ne peut PAS modifier les permissions des agents
        if request.user.is_admin:
            if target_user.role == User.Role.AGENT:
                return Response(
                    {"error": "L'admin ne peut pas modifier les permissions des agents."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ✅ Le manager ne peut modifier que les permissions de SES propres agents
        if request.user.is_manager:
            if target_user.role != User.Role.AGENT or target_user.branch != request.user.branch:
                return Response(
                    {"error": "Vous ne pouvez modifier que les permissions de vos agents."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = UpdateUserPermissionsSerializer(
            target_user,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        return Response(
            {
                "message": "Permissions mises à jour avec succès.",
                "user_id": str(target_user.id),
                "permissions_list": target_user.permissions_list,
            },
            status=status.HTTP_200_OK,
        )


class UpdateUserStatusView(APIView):
    """
    PATCH /api/auth/users/{id}/status/

    Permet à l'admin de suspendre ou réactiver un compte utilisateur.
    Accessible uniquement à l'admin.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # L'admin ne peut pas modifier son propre statut
        if target_user.id == request.user.id:
            return Response(
                {"error": "Vous ne pouvez pas modifier votre propre statut."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UpdateUserStatusSerializer(
            target_user,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        if new_status == User.AccountStatus.SUSPENDED:
            target_user.suspend(reason=reason)
            # Révocation de toutes les sessions de l'utilisateur suspendu
            from apps.token_security.services import TokenService
            TokenService.revoke_all_user_tokens(user=target_user, reason="admin_revoked")
            message = f"Le compte de {target_user.email} a été suspendu."
        else:
            target_user.activate()
            message = f"Le compte de {target_user.email} a été réactivé."

        return Response({"message": message}, status=status.HTTP_200_OK)


class AllUsersListView(APIView):
    """
    GET /api/auth/users/

    Retourne la liste de tous les utilisateurs.
    Accessible uniquement à l'admin.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        role_filter = request.query_params.get("role")
        status_filter = request.query_params.get("status")

        users = User.objects.exclude(id=request.user.id)

        if role_filter:
            users = users.filter(role=role_filter)
        if status_filter:
            users = users.filter(status=status_filter)

        serializer = UserListSerializer(users, many=True)
        return Response(
            {
                "count": users.count(),
                "users": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
class AssignBranchView(APIView):
    """
    PATCH /api/auth/users/{id}/assign-branch/

    - Admin : assigne une succursale à un manager
    - Manager : assigne SA succursale à ses agents
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 🔴 CAS 1 — ADMIN → MANAGER
        if request.user.is_admin:
            if target_user.role != User.Role.MANAGER:
                return Response(
                    {"error": "L'admin peut assigner une succursale uniquement à un manager."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            branch = request.data.get("branch")
            if not branch:
                return Response(
                    {"error": "Le champ 'branch' est requis."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            target_user.branch_id = branch
            target_user.save(update_fields=["branch"])

            return Response(
                {
                    "message": "Succursale assignée au manager avec succès.",
                    "manager_id": str(target_user.id),
                    "branch": branch,
                },
                status=status.HTTP_200_OK,
            )

        # 🔵 CAS 2 — MANAGER → AGENT
        if request.user.is_manager:
            if target_user.role != User.Role.AGENT:
                return Response(
                    {"error": "Un manager ne peut assigner une succursale qu'à ses agents."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if target_user.branch and target_user.branch != request.user.branch:
                return Response(
                    {"error": "Cet agent appartient déjà à une autre succursale."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            target_user.branch = request.user.branch
            target_user.save(update_fields=["branch"])

            return Response(
                {
                    "message": "Agent assigné à votre succursale avec succès.",
                    "agent_id": str(target_user.id),
                    "branch": str(request.user.branch.id),
                },
                status=status.HTTP_200_OK,
            )

        # ❌ AUTRES CAS
        return Response(
            {"error": "Action non autorisée."},
            status=status.HTTP_403_FORBIDDEN,
        )
