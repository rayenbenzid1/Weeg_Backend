import uuid
from django.db import models


class InventorySnapshot(models.Model):
    """
    Represents a horizontal inventory record imported from the Excel file
    (جرد_افقي_نهاية_السنة).

    One row per product, storing stock quantities and values
    broken down by branch. This is a point-in-time snapshot,
    tagged with a snapshot_date (typically end of year).

    The branch quantities/values are stored as flat fields rather than
    separate rows to preserve the original horizontal Excel structure and
    allow fast cross-branch comparison queries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="inventory_snapshots",
        verbose_name="Company",
    )

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="inventory_snapshots",
        verbose_name="Product",
    )

    snapshot_date = models.DateField(
        verbose_name="Snapshot Date",
        help_text="Date of this inventory snapshot (e.g. 2025-12-31).",
    )

    # ── Per-branch quantities ─────────────────────────────────────────────────

    qty_alkarimia = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Al-Karimia Branch",
    )
    qty_benghazi = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Benghazi Warehouse",
    )
    qty_mazraa = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Al-Mazraa Warehouse",
    )
    qty_dahmani = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Dahmani Showroom",
    )
    qty_janzour = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Janzour Showroom",
    )
    qty_misrata = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Qty — Misrata Branch",
    )

    # ── Per-branch values (LYD) ───────────────────────────────────────────────

    value_mazraa = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Value — Al-Mazraa Warehouse",
    )
    value_dahmani = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Value — Dahmani Showroom",
    )
    value_janzour = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Value — Janzour Showroom",
    )
    value_alkarimia = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Value — Al-Karimia Branch",
    )
    value_misrata = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Value — Misrata Branch",
    )

    # ── Totals ────────────────────────────────────────────────────────────────

    total_qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Total Quantity",
    )
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        default=0,
        verbose_name="Cost Price (LYD)",
        help_text="Company cost price per unit.",
    )
    total_value = models.DecimalField(
        max_digits=18, decimal_places=4,
        default=0,
        verbose_name="Total Value (LYD)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_snapshot"
        verbose_name = "Inventory Snapshot"
        verbose_name_plural = "Inventory Snapshots"
        ordering = ["-snapshot_date", "product__category", "product__product_name"]
        unique_together = [("company", "product", "snapshot_date")]

    def __str__(self):
        return f"{self.product} — {self.snapshot_date} ({self.total_qty} units)"

    @property
    def total_branches_value(self):
        """Sum of all branch values."""
        return (
            self.value_mazraa + self.value_dahmani +
            self.value_janzour + self.value_alkarimia +
            self.value_misrata
        )
