import uuid
from django.db import models


class Branch(models.Model):
    """
    Represents a branch (agency/office) of the company.
    Each agent and manager is assigned to one branch.
    Data (stock, sales, KPIs) is filtered by branch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Branch name",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Address",
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="City",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Phone",
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Branch email",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Disabling a branch hides it without deleting its data.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last updated")

    class Meta:
        db_table = "branches_branch"
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city or 'City not specified'})"