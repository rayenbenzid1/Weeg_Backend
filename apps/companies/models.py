import uuid
from django.db import models


class Company(models.Model):
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

    country = models.CharField(          # ← ADD
        max_length=100,
        blank=True,
        default='',
        verbose_name="Country",
    )

    city = models.CharField(             # ← ADD
        max_length=100,
        blank=True,
        default='',
        verbose_name="City",
    )

    current_erp = models.CharField(      # ← ADD
        max_length=100,
        blank=True,
        default='',
        verbose_name="Current ERP",
        help_text="ERP or software currently used by the company.",
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