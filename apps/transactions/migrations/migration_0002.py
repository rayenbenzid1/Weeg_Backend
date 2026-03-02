# Generated manually — removes choices constraint from movement_type,
# drops movement_type_raw (now redundant), migrates existing data.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0001_initial'),
    ]

    operations = [
        # Step 1 — Alter movement_type: remove choices, increase max_length
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(
                max_length=100,
                verbose_name='Movement Type',
                db_index=True,
                blank=True,
                default='',
                help_text='Raw Arabic movement type label stored as-is from Excel.',
            ),
        ),

        # Step 2 — Migrate existing English-mapped values back to Arabic
        migrations.RunSQL(
            sql="""
                UPDATE transactions_movement SET movement_type = CASE movement_type
                    WHEN 'sale'             THEN 'ف بيع'
                    WHEN 'purchase'         THEN 'ف شراء'
                    WHEN 'opening_balance'  THEN 'ف.أول المدة'
                    WHEN 'sales_return'     THEN 'مردودات بيع'
                    WHEN 'purchase_return'  THEN 'مردود شراء'
                    WHEN 'main_entry'       THEN 'ادخال رئيسي'
                    WHEN 'main_exit'        THEN 'اخراج رئيسي'
                    WHEN 'other'            THEN movement_type_raw
                    ELSE movement_type
                END
                WHERE movement_type IN (
                    'sale','purchase','opening_balance',
                    'sales_return','purchase_return',
                    'main_entry','main_exit','other'
                );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Step 3 — Drop movement_type_raw (now redundant)
        migrations.RemoveField(
            model_name='materialmovement',
            name='movement_type_raw',
        ),
    ]