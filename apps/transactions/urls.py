# apps/transactions/urls.py
from django.urls import path
from .views import (
    MaterialMovementListView,
    MaterialMovementDetailView,
)

app_name = "transactions"

urlpatterns = [
    # Liste + filtres
    path('movements/', MaterialMovementListView.as_view(), name='movement-list'),
    
    # Détail d'un mouvement
    path('movements/<uuid:pk>/', MaterialMovementDetailView.as_view(), name='movement-detail'),
    
    # Possibles ajouts futurs :
    # path('movements/create/', ... , name='movement-create'),
    # path('movements/<uuid:pk>/update/', ...),
    # path('movements/<uuid:pk>/delete/', ...),
]