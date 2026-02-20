from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin
from .models import Branch
from .serializers import BranchSerializer


class BranchListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branches = Branch.objects.filter(is_active=True)
        serializer = BranchSerializer(branches, many=True)
        return Response({"branches": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        if not request.user.is_admin:
            return Response(
                {"error": "Seul un administrateur peut créer une succursale."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = BranchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)