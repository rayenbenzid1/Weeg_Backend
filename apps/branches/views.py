from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin

from .models import Branch, BranchAlias  
from .serializers import BranchSerializer, BranchAliasSerializer 
class BranchListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branches = Branch.objects.filter(is_active=True)
        serializer = BranchSerializer(branches, many=True)
        return Response({"branches": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        if not request.user.is_admin:
            return Response(
                {"error": "Only an administrator can create a branch."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = BranchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
class BranchAliasListView(APIView):
    """
    GET   /api/branches/aliases/
          ?unresolved=true   → only aliases with no branch assigned
          ?search=<str>      → filter by alias string

    PATCH /api/branches/aliases/
          body: { "alias_id": "<uuid>", "branch_id": "<uuid>" }
          → manually resolve an alias
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            BranchAlias.objects
            .filter(company=request.user.company)
            .select_related("branch")
            .order_by("alias")
        )

        if request.query_params.get("unresolved") == "true":
            qs = qs.filter(branch__isnull=True)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(alias__icontains=search)

        serializer = BranchAliasSerializer(qs, many=True)
        return Response({
            "count":   qs.count(),
            "aliases": serializer.data,
        })

    def patch(self, request):
        alias_id  = request.data.get("alias_id")
        branch_id = request.data.get("branch_id")

        if not alias_id or not branch_id:
            return Response(
                {"error": "Both alias_id and branch_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            alias = BranchAlias.objects.get(
                id=alias_id,
                company=request.user.company,
            )
        except BranchAlias.DoesNotExist:
            return Response({"error": "Alias not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        alias.branch       = branch
        alias.auto_matched = False   # manually resolved
        alias.save(update_fields=["branch", "auto_matched"])

        return Response({
            "id":          str(alias.id),
            "alias":       alias.alias,
            "branch_id":   str(branch.id),
            "branch_name": branch.name,
            "resolved":    True,
        })


class BranchAliasDetailView(APIView):
    """
    DELETE /api/branches/aliases/<uuid>/   → remove an alias entirely
    """
    permission_classes = [IsAuthenticated]

    def _get_alias(self, request, alias_id):
        try:
            return BranchAlias.objects.get(id=alias_id, company=request.user.company)
        except BranchAlias.DoesNotExist:
            return None

    def delete(self, request, alias_id):
        alias = self._get_alias(request, alias_id)
        if not alias:
            return Response({"error": "Alias not found."}, status=status.HTTP_404_NOT_FOUND)
        alias.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BranchAliasUnresolvedCountView(APIView):
    """
    GET /api/branches/aliases/unresolved-count/
    Lightweight endpoint for dashboard badges / notifications.
    Returns: { "count": <int> }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = BranchAlias.objects.filter(
            company=request.user.company,
            branch__isnull=True,
        ).count()
        return Response({"count": count})
