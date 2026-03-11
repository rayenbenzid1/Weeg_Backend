from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0004_alter_user_options_alter_user_branch_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="branch",
        ),
    ]
