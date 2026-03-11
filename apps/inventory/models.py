import uuid
from django.conf import settings
from django.db import models


class InventorySnapshot(models.Model):
    """
    One record per imported Excel inventory file (جرد).

    Fully autonomous — no FK to companies_company, no FK to branches_branch.
    company_name and branch names are stored as plain text.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_snapshots",
        verbose_name="Company",
    )
    company_name = models.CharField(
        max_length=200,
        verbose_name="Company Name",
        help_text="Name of the company that owns this inventory snapshot.",
    )
    inventory_year = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Inventory Year",
        help_text="4-digit fiscal year extracted from the uploaded filename.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Label",
        help_text="Optional human-readable label (e.g. 'Inventaire 2025 T1').",
    )
    snapshot_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Snapshot Date",
    )
    fiscal_year = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="Fiscal Year",
    )
    source_file = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Source File",
    )
    notes = models.TextField(blank=True, default="", verbose_name="Notes")

    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Uploaded At")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_snapshots",
        verbose_name="Uploaded By",
    )

    class Meta:
        db_table = "inventory_snapshot"
        verbose_name = "Inventory Snapshot"
        verbose_name_plural = "Inventory Snapshots"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.company_name} — {self.label or self.source_file} ({self.uploaded_at.date()})"


class InventorySnapshotLine(models.Model):
    """
    One row per (product × branch) within an InventorySnapshot.

    Produced by melting a horizontal Excel row into vertical lines.
    branch_name is plain text — no FK to branches_branch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    snapshot = models.ForeignKey(
        InventorySnapshot,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Snapshot",
    )

    product_category = models.CharField(
        max_length=200, blank=True, default="", verbose_name="Category",
    )
    product_code = models.CharField(max_length=100, verbose_name="Product Code")
    product_name = models.CharField(
        max_length=500, blank=True, default="", verbose_name="Product Name",
    )

    branch_name = models.CharField(
        max_length=200,
        verbose_name="Branch Name",
        help_text="Plain-text branch name extracted from the Excel header. No FK.",
    )

    quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=0, verbose_name="Quantity",
    )
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=4, default=0, verbose_name="Unit Cost",
    )
    line_value = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, verbose_name="Line Value",
    )

    class Meta:
        db_table = "inventory_snapshot_line"
        verbose_name = "Inventory Snapshot Line"
        verbose_name_plural = "Inventory Snapshot Lines"
        ordering = ["product_code", "branch_name"]
        unique_together = [("snapshot", "product_code", "branch_name")]

    def __str__(self):
        return f"{self.product_code} | {self.branch_name} | qty={self.quantity}"
