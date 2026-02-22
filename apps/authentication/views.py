import logging
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import threading

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
from .email_service import (
    notify_admin_new_manager,
    notify_manager_approved,
    notify_manager_rejected,
)
from .services import UserService

logger = logging.getLogger("django")
User = get_user_model()


class ProfileView(APIView):
    """
    GET  /api/auth/profile/  → Display the profile of the logged-in user
    PATCH /api/auth/profile/ → Update profile information

    Accessible to all roles (admin, manager, agent).
    Only non-sensitive fields are editable (first name, last name, phone).
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
                "message": "Profile updated successfully.",
                "user": UserProfileSerializer(request.user).data,
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/

    Allows a logged-in user to change their own password.
    Requires the old password for validation.

    Upon success:
        - token_version incremented → all old tokens invalidated
        - must_change_password set to False (for agents on first login)
        - Confirmation email sent
        - All sessions revoked (user must log in again)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Check old password
        if not request.user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"error": "The old password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserService.change_password(
            user=request.user,
            new_password=serializer.validated_data["new_password"],
            request=request,
        )

        return Response(
            {
                "message": "Password changed successfully. "
                           "All your sessions have been closed. Please log in again."
            },
            status=status.HTTP_200_OK,
        )


# class CreateAgentView(APIView):
#     """
#     POST /api/auth/agents/

#     Allows a manager to create an agent account.
#     The manager can only create agents for their own branch.

#     Request body:
#         - email, first_name, last_name, phone_number
#         - branch: UUID of the branch (must be the manager's)
#         - permissions_list: list of permissions to grant
#         - temporary_password: temporary password

#     Upon success:
#         - Agent account created with must_change_password = True
#         - Email with credentials sent to the agent
#     """
#     permission_classes = [IsAuthenticated, IsManager]

#     def post(self, request):
#         serializer = CreateAgentSerializer(
#             data=request.data,
#             context={"request": request},
#         )
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         # Check that the branch belongs to the logged-in manager
#         branch = serializer.validated_data.get("branch")
#         if branch and request.user.branch and branch.id != request.user.branch.id:
#             return Response(
#                 {"error": "You can only create agents for your own branch."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         temporary_password = request.data.get("temporary_password")
#         agent = UserService.create_agent(
#             validated_data=serializer.validated_data,
#             manager=request.user,
#             temporary_password=temporary_password,
#         )

#         return Response(
#             {
#                 "message": f"Agent account created successfully. "
#                            f"Credentials have been sent to {agent.email}.",
#                 "agent": UserListSerializer(agent).data,
#             },
#             status=status.HTTP_201_CREATED,
#         )

class CreateAgentView(APIView):
    """
    POST /api/users/agents/create/

    Allows a manager to create an agent account.
    The agent's Company is automatically that of the Manager — no input required.
    """
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request):
        serializer = CreateAgentSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Optional branch check (if provided, must belong to the manager)
        branch = serializer.validated_data.get("branch")
        if branch and request.user.branch and branch.id != request.user.branch.id:
            return Response(
                {"error": "You can only create agents for your own branch."},
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
                "message": f"Agent account created successfully. Credentials have been sent to {agent.email}.",
                "agent": UserListSerializer(agent).data,
            },
            status=status.HTTP_201_CREATED,
        )

# class AgentListView(APIView):
#     """
#     GET /api/users/agents/

#     ✅ Manager → sees only agents from THEIR branch.
#     ✅ Admin   → sees ALL agents from all branches.
#     ❌ Agent   → 403 Forbidden.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     def get(self, request):
#         if request.user.is_admin:
#             # Admin sees all agents from all branches
#             agents = User.objects.filter(
#                 role=User.Role.AGENT,
#             ).order_by("-created_at")
#         else:
#             # Manager sees only agents from their branch
#             agents = User.objects.filter(
#                 role=User.Role.AGENT,
#                 branch=request.user.branch,
#             ).order_by("-created_at")

#         serializer = UserListSerializer(agents, many=True)
#         return Response(
#             {
#                 "count": agents.count(),
#                 "agents": serializer.data,
#             },
#             status=status.HTTP_200_OK,
#         )


class AgentListView(APIView):
    """
    GET /api/users/agents/

    Manager → agents from THEIR company only.
    Admin   → all agents.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    def get(self, request):
        if request.user.is_admin:
            agents = User.objects.filter(role=User.Role.AGENT).order_by("-created_at")
        else:
            # Manager sees agents from their own Company
            agents = User.objects.filter(
                role=User.Role.AGENT,
                company=request.user.company,
            ).order_by("-created_at")

        serializer = UserListSerializer(agents, many=True)
        return Response(
            {"count": agents.count(), "agents": serializer.data},
            status=status.HTTP_200_OK,
        )

class AgentDetailView(APIView):
    """
    GET    /api/auth/agents/{id}/  → Agent details
    PATCH  /api/auth/agents/{id}/  → Update an agent (manager only)
    DELETE /api/auth/agents/{id}/  → Delete an agent (SCRUM-43)

    The manager can only access agents from their own branch.
    """
    permission_classes = [IsAuthenticated, IsManager]

    def _get_agent(self, agent_id, manager):
        """Retrieve the agent by checking it belongs to the manager's branch."""
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
                {"error": "Agent not found or unauthorized access."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserListSerializer(agent)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, agent_id):
        agent = self._get_agent(agent_id, request.user)
        if not agent:
            return Response(
                {"error": "Agent not found or unauthorized access."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UpdateProfileSerializer(agent, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(
            {
                "message": "Agent profile updated successfully.",
                "agent": UserListSerializer(agent).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, agent_id):
        """
        Delete an agent account (SCRUM-43).
        Revoke all their sessions before deletion.
        """
        from apps.token_security.services import TokenService

        agent = self._get_agent(agent_id, request.user)
        if not agent:
            return Response(
                {"error": "Agent not found or unauthorized access."},
                status=status.HTTP_404_NOT_FOUND,
            )

        agent_email = agent.email
        TokenService.revoke_all_user_tokens(user=agent, reason="admin_revoked")
        agent.delete()

        logger.info(
            f"Agent [{agent_email}] deleted by manager [{request.user.email}]."
        )

        return Response(
            {"message": f"The account of {agent_email} has been deleted successfully."},
            status=status.HTTP_200_OK,
        )


class UpdateUserPermissionsView(APIView):
    """
    PATCH /api/users/users/{id}/permissions/

    Access rules:
        ✅ Manager → can modify permissions of THEIR agents only.
        ❌ Admin   → does NOT have the right to modify agent permissions.
        ❌ Agent   → Access denied (IsAdminOrManager blocks).

    To view agents, admin uses GET /api/users/users/?role=agent.
    (SCRUM-20)
    """
    # ✅ Keep IsAdminOrManager to block agents (403)
    # ❌ But add explicit check: admin cannot modify agents
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    def patch(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ✅ MODIFICATION: Admin cannot modify agent permissions
        if request.user.is_admin:
            if target_user.role == User.Role.AGENT:
                return Response(
                    {"error": "Admin cannot modify agent permissions."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ✅ Manager can only modify permissions of THEIR own agents
        if request.user.is_manager:
            if target_user.role != User.Role.AGENT or target_user.branch != request.user.branch:
                return Response(
                    {"error": "You can only modify permissions of your agents."},
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
                "message": "Permissions updated successfully.",
                "user_id": str(target_user.id),
                "permissions_list": target_user.permissions_list,
            },
            status=status.HTTP_200_OK,
        )


class UpdateUserStatusView(APIView):
    """
    PATCH /api/auth/users/{id}/status/

    Allows admin to suspend or reactivate a user account.
    Accessible only to admin.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, user_id):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Admin cannot modify their own status
        if target_user.id == request.user.id:
            return Response(
                {"error": "You cannot modify your own status."},
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
            # Revoke all sessions of the suspended user
            from apps.token_security.services import TokenService
            TokenService.revoke_all_user_tokens(user=target_user, reason="admin_revoked")
            message = f"The account of {target_user.email} has been suspended."
        else:
            target_user.activate()
            message = f"The account of {target_user.email} has been reactivated."

        return Response({"message": message}, status=status.HTTP_200_OK)


class AllUsersListView(APIView):
    """
    GET /api/auth/users/

    Returns the list of all users.
    Accessible only to admin.
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

def _send_async(fn, *args, **kwargs):
    """
    Launches email sending in a separate thread to not block the HTTP response.
    """
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()