"""
Migration 0006 – Radical redesign of the inventory app.

Replaces the old single-row-per-product InventorySnapshot table with:

  InventorySnapshot        — one record per imported Excel file (session metadata)
  InventorySnapshotLine    — one row per (product × branch) produced by horizontal melt

All FK references to companies_company, products_product, and branches_branch
are removed.  company_name and branch_name are stored as plain text.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_branch_quantities_to_branch_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Step 1 ── Drop the entire old inventory_snapshot table ────────────
        migrations.DeleteModel(
            name="InventorySnapshot",
        ),
        # ── Step 2 ── Recreate inventory_snapshot with new schema ─────────────
        migrations.CreateModel(
            name="InventorySnapshot",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "company_name",
                    models.CharField(
                        help_text="Name of the company that owns this inventory snapshot.",
                        max_length=200,
                        verbose_name="Company Name",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=200,
                        verbose_name="Label",
                    ),
                ),
                (
                    "snapshot_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Snapshot Date",
                    ),
                ),
                (
                    "fiscal_year",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=10,
                        verbose_name="Fiscal Year",
                    ),
                ),
                (
                    "source_file",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="Source File",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Notes",
                    ),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Uploaded At",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_snapshots",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Uploaded By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Inventory Snapshot",
                "verbose_name_plural": "Inventory Snapshots",
                "db_table": "inventory_snapshot",
                "ordering": ["-uploaded_at"],
            },
        ),
        # ── Step 3 ── Create inventory_snapshot_line ──────────────────────────
        migrations.CreateModel(
            name="InventorySnapshotLine",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="inventory.inventorysnapshot",
                        verbose_name="Snapshot",
                    ),
                ),
                (
                    "product_category",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=200,
                        verbose_name="Category",
                    ),
                ),
                (
                    "product_code",
                    models.CharField(
                        max_length=100,
                        verbose_name="Product Code",
                    ),
                ),
                (
                    "product_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="Product Name",
                    ),
                ),
                (
                    "branch_name",
                    models.CharField(
                        help_text="Plain-text branch name extracted from the Excel header. No FK.",
                        max_length=200,
                        verbose_name="Branch Name",
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                        verbose_name="Quantity",
                    ),
                ),
                (
                    "unit_cost",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                        verbose_name="Unit Cost",
                    ),
                ),
                (
                    "line_value",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=18,
                        verbose_name="Line Value",
                    ),
                ),
            ],
            options={
                "verbose_name": "Inventory Snapshot Line",
                "verbose_name_plural": "Inventory Snapshot Lines",
                "db_table": "inventory_snapshot_line",
                "ordering": ["product_code", "branch_name"],
            },
        ),
        # ── Step 4 ── Add unique constraint on (snapshot, product_code, branch_name)
        migrations.AlterUniqueTogether(
            name="inventorysnapshotline",
            unique_together={("snapshot", "product_code", "branch_name")},
        ),
    ]
