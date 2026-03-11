import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0002_alter_branch_options_alter_branch_address_and_more"),
        ("inventory", "0002_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="inventorysnapshot",
            options={
                "db_table": "inventory_snapshot",
                "ordering": ["-created_at", "product__category", "product__product_name"],
                "verbose_name": "Inventory Snapshot",
                "verbose_name_plural": "Inventory Snapshots",
            },
        ),
        migrations.AlterUniqueTogether(
            name="inventorysnapshot",
            unique_together={("company", "product")},
        ),
        migrations.RemoveField(model_name="inventorysnapshot", name="snapshot_date"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_alkarimia"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_benghazi"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_mazraa"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_dahmani"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_janzour"),
        migrations.RemoveField(model_name="inventorysnapshot", name="qty_misrata"),
        migrations.RemoveField(model_name="inventorysnapshot", name="value_alkarimia"),
        migrations.RemoveField(model_name="inventorysnapshot", name="value_mazraa"),
        migrations.RemoveField(model_name="inventorysnapshot", name="value_dahmani"),
        migrations.RemoveField(model_name="inventorysnapshot", name="value_janzour"),
        migrations.RemoveField(model_name="inventorysnapshot", name="value_misrata"),
        migrations.CreateModel(
            name="InventoryBranchValue",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("value", models.DecimalField(decimal_places=4, default=0, max_digits=18, verbose_name="Branch Value (LYD)")),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_values",
                        to="branches.branch",
                        verbose_name="Branch",
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="branch_values",
                        to="inventory.inventorysnapshot",
                        verbose_name="Inventory Snapshot",
                    ),
                ),
            ],
            options={
                "db_table": "inventory_branch_value",
                "verbose_name": "Inventory Branch Value",
                "verbose_name_plural": "Inventory Branch Values",
                "unique_together": {("snapshot", "branch")},
            },
        ),
    ]
