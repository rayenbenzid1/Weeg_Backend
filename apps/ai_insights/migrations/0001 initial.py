import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("companies", "0004_company_city_company_country_company_current_erp"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertResolution",
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
                    "alert_id",
                    models.CharField(
                        db_index=True,
                        max_length=255,
                        verbose_name="Alert ID",
                    ),
                ),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("overdue",          "Overdue Payment"),
                            ("risk",             "Credit Risk"),
                            ("low_stock",        "Low Stock"),
                            ("sales_drop",       "Sales Drop"),
                            ("high_receivables", "High Receivables"),
                            ("churn",            "Churn Risk"),
                        ],
                        max_length=50,
                        verbose_name="Alert Type",
                    ),
                ),
                (
                    "resolved_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Resolved At",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Resolution Notes",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert_resolutions",
                        to="companies.company",
                        verbose_name="Company",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_alerts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Resolved By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Alert Resolution",
                "verbose_name_plural": "Alert Resolutions",
                "db_table": "ai_alert_resolution",
                "ordering": ["-resolved_at"],
                "unique_together": {("company", "alert_id")},
            },
        ),
    ]