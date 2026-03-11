import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("inventory", "0006_radical_redesign"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventorysnapshot",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="inventory_snapshots",
                to="companies.company",
                verbose_name="Company",
            ),
        ),
        migrations.AddField(
            model_name="inventorysnapshot",
            name="inventory_year",
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name="Inventory Year",
                help_text="4-digit fiscal year extracted from the uploaded filename.",
            ),
        ),
    ]
