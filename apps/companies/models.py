import uuid
from django.db import models


class Company(models.Model):
    """
    Modèle représentant une société (entreprise cliente).

    Hiérarchie :
        Company → Branch (plusieurs succursales par société)
        Company → Manager (chaque manager appartient à une société)
        Company → Agent  (via son manager, même société)

    Une Company est créée automatiquement lors de l'inscription d'un Manager
    (si elle n'existe pas déjà) ou peut être pré-créée par l'Admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de la société",
        help_text="Nom officiel de la société.",
    )

    industry = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Secteur d'activité",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Désactiver pour suspendre l'accès à toute la société.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    class Meta:
        db_table = "company"
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"
        ordering = ["name"]

    def __str__(self):
        return self.name
