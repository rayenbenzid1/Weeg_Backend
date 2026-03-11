from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("kpi", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="RiskyCustomerSnapshot",
        ),
        migrations.DeleteModel(
            name="KPISnapshot",
        ),
    ]
