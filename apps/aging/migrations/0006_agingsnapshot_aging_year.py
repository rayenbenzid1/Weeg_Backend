from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aging", "0005_alter_agingreceivable_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="agingsnapshot",
            name="aging_year",
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name="Aging Year",
                help_text="4-digit fiscal year extracted from the uploaded filename.",
            ),
        ),
    ]
