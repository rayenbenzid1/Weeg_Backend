from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin
from .models import Company
from .serializers import CompanySerializer


class CompanyListView(APIView):
    """
    GET  /api/companies/       → List all companies (admin only)
    POST /api/companies/       → Create a company (admin only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        companies = Company.objects.all()
        serializer = CompanySerializer(companies, many=True)
        return Response({"count": companies.count(), "companies": serializer.data})

    def post(self, request):
        serializer = CompanySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    """
    GET   /api/companies/{id}/  → Detail (admin only)
    PATCH /api/companies/{id}/  → Update (admin only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_company(self, company_id):
        try:
            return Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return None

    def get(self, request, company_id):
        company = self._get_company(company_id)
        if not company:
            return Response({"error": "Société introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CompanySerializer(company).data)

    def patch(self, request, company_id):
        company = self._get_company(company_id)
        if not company:
            return Response({"error": "Société introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)
