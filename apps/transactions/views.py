# apps/transactions/views.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import MaterialMovement
from .serializers import MaterialMovementSerializer, MaterialMovementMinimalSerializer


class MaterialMovementListView(APIView):
    """
    GET /api/transactions/movements/
    Liste des mouvements de matières pour l'entreprise de l'utilisateur connecté.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'movement_date': ['exact', 'gte', 'lte'],
        'movement_type': ['exact', 'in'],
        'material_code': ['exact', 'icontains'],
        'branch__name': ['icontains'],
        'customer__name': ['icontains'],
    }
    search_fields = [
        'material_code', 'material_name', 'lab_code',
        'branch_name', 'customer_name', 'movement_type_raw'
    ]
    ordering_fields = [
        'movement_date', 'material_code', 'movement_type',
        'total_in', 'total_out', 'created_at'
    ]
    ordering = ['-movement_date']

    def get(self, request):
        if not request.user.company:
            return Response(
                {"error": "No company associated with your account."},
                status=status.HTTP_403_FORBIDDEN
            )

        queryset = MaterialMovement.objects.filter(
            company=request.user.company
        ).select_related(
            'product', 'branch', 'customer'
        ).order_by('-movement_date')

        # Appliquer les filtres manuellement si besoin (ou via django-filter)
        queryset = self.filter_queryset(queryset)

        # Utiliser serializer léger pour les listes
        serializer = MaterialMovementMinimalSerializer(queryset[:500], many=True)
        
        return Response({
            "count": queryset.count(),
            "results": serializer.data
        })

    def filter_queryset(self, queryset):
        # django-filter n'est pas directement utilisable sur APIView
        # → on peut implémenter les filtres ici ou passer à generics.ListAPIView
        return queryset


class MaterialMovementDetailView(APIView):
    """
    GET /api/transactions/movements/{id}/
    Détails d'un mouvement spécifique (doit appartenir à la compagnie)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, company):
        try:
            return MaterialMovement.objects.get(id=pk, company=company)
        except MaterialMovement.DoesNotExist:
            return None

    def get(self, request, pk):
        if not request.user.company:
            return Response({"error": "No company found"}, status=403)

        movement = self.get_object(pk, request.user.company)
        if not movement:
            return Response({"error": "Movement not found or not accessible"}, status=404)

        serializer = MaterialMovementSerializer(movement)
        return Response(serializer.data)