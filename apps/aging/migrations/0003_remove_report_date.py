from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("aging", "0002_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="agingreceivable",
            unique_together={("company", "account_code")},
        ),
        migrations.RemoveField(
            model_name="agingreceivable",
            name="report_date",
        ),
    ]
