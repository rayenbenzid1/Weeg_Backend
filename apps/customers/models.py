"""
apps/customers/models.py

Clients de la société.
"""

import uuid
from django.db import models


class Customer(models.Model):
    """
    Client importé depuis le fichier العملاء.xlsx
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customers",
        verbose_name="Company",
    )

    account_code = models.CharField(
        max_length=50,
        verbose_name="Account code",
        help_text="رمز الحساب",
        db_index=True,
    )

    name = models.CharField(
        max_length=500,
        verbose_name="Customer name",
        help_text="اسم العميل",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Address",
        help_text="العنوان التفصيلي",
    )

    area_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Area code",
        help_text="رمز المنطقة",
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Phone",
        help_text="رقم الهاتف1",
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        db_index=True,
        help_text="Set to False when absent from import — preserves FK integrity.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["name"]
        unique_together = [("company", "account_code")]

    def __str__(self):
        return f"[{self.account_code}] {self.name}"
