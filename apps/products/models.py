import uuid
from django.db import models


class Product(models.Model):
    """
    Represents a product/material extracted from Excel import files.

    Products are scoped per company. The product_code is the unique
    business identifier used across all import files to link records.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Company",
    )

    product_code = models.CharField(
        max_length=100,
        verbose_name="Product Code",
        help_text="Unique product/material code from the accounting system.",
    )

    lab_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Lab / Supplier Code",
    )

    product_name = models.CharField(
        max_length=500,
        verbose_name="Product Name",
    )

    category = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Category",
        help_text="Product category/family (e.g. Fire Detection, Addressable).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_product"
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["category", "product_name"]
        unique_together = [("company", "product_code")]

    def __str__(self):
        return f"[{self.product_code}] {self.product_name}"
