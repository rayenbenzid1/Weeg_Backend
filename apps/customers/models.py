import uuid
from django.db import models


class Customer(models.Model):
    """
    Represents a client imported from the Excel customers file (العملاء).

    Each Customer belongs to a Company, allowing multi-tenant isolation.
    The account_code is the unique business identifier from the accounting system.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customers",
        verbose_name="Company",
    )

    customer_name = models.CharField(
        max_length=500,
        verbose_name="Customer Name",
    )

    account_code = models.CharField(
        max_length=100,
        verbose_name="Account Code",
        help_text="Unique accounting system identifier (e.g. 113102).",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Address",
    )

    area_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Area Code",
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Phone",
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customers_customer"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["customer_name"]
        # One account_code per company
        unique_together = [("company", "account_code")]

    def __str__(self):
        return f"{self.customer_name} ({self.account_code})"
