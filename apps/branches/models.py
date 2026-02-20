import uuid
from django.db import models


class Branch(models.Model):
    """
    Représente une succursale (agence) de l'entreprise.
    Chaque agent et manager est assigné à une succursale.
    Les données (stock, ventes, KPIs) sont filtrées par succursale.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Nom de la succursale",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse",
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Ville",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone",
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email de la succursale",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Désactiver une succursale la masque sans supprimer ses données.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "branches_branch"
        verbose_name = "Succursale"
        verbose_name_plural = "Succursales"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city or 'Ville non renseignée'})"