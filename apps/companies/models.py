import uuid
from django.db import models


class Company(models.Model):
    """
    Model representing a company (client organization).

    Hierarchy:
        Company → Branch (multiple branches per company)
        Company → Manager (each manager belongs to one company)
        Company → Agent   (via their manager, same company)

    A Company is automatically created when a Manager registers
    (if it doesn't already exist) or can be pre-created by an Admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Company name",
        help_text="Official name of the company.",
    )

    industry = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Industry / Sector",
        help_text="Main business sector or industry.",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Phone number",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Address",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Is active",
        help_text="Disable to suspend access for the entire company.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last modified")

    class Meta:
        db_table = "company"
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return self.name