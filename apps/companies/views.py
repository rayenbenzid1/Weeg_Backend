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
    POST /api/companies/       → Create a new company (admin only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Return a list of all companies with total count."""
        companies = Company.objects.all()
        serializer = CompanySerializer(companies, many=True)
        return Response({
            "count": companies.count(),
            "companies": serializer.data
        })

    def post(self, request):
        """Create a new company (admin only)."""
        serializer = CompanySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    """
    GET   /api/companies/{id}/  → Retrieve company details (admin only)
    PATCH /api/companies/{id}/  → Partial update of a company (admin only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_company(self, company_id):
        try:
            return Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return None

    def get(self, request, company_id):
        """Retrieve details of a specific company."""
        company = self._get_company(company_id)
        if not company:
            return Response(
                {"error": "Company not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CompanySerializer(company)
        return Response(serializer.data)

    def patch(self, request, company_id):
        """Partially update a company (admin only)."""
        company = self._get_company(company_id)
        if not company:
            return Response(
                {"error": "Company not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CompanySerializer(company, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer.save()
        return Response(serializer.data)