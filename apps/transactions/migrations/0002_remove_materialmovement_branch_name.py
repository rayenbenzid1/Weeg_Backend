from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0001_alter_materialmovement_movement_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="materialmovement",
            name="branch_name",
        ),
    ]
