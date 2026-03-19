"""
Migration à créer dans apps/ai_insights/migrations/
Cette migration ajoute le modèle AIUsageLog pour suivre la consommation de tokens AI par entreprise.
Le modèle AIUsageLog contient les champs suivants :
- id : UUID primary key
- analyzer : nom de l'analyseur ou fonctionnalité qui a généré l'appel AI (ex: "churn_prediction", "alert_explanation")

"""

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
    ("ai_insights", "0002_alter_alertresolution_notes"),
    ("companies",   "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIUsageLog",
            fields=[
                ("id",          models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ("analyzer",    models.CharField(db_index=True, max_length=50,
                                                 verbose_name="Analyzer")),
                ("model",       models.CharField(max_length=100, verbose_name="AI Model")),
                ("tokens_used", models.IntegerField(default=0, verbose_name="Tokens Used")),
                ("cost_usd",    models.DecimalField(decimal_places=8, default=0,
                                                    max_digits=10,
                                                    verbose_name="Estimated Cost (USD)")),
                ("created_at",  models.DateTimeField(auto_now_add=True, db_index=True,
                                                     verbose_name="Timestamp")),
                ("company",     models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ai_usage_logs",
                    to="companies.company",
                    verbose_name="Company",
                )),
            ],
            options={
                "verbose_name":        "AI Usage Log",
                "verbose_name_plural": "AI Usage Logs",
                "db_table":            "ai_usage_log",
                "ordering":            ["-created_at"],
            },
        ),
    ]