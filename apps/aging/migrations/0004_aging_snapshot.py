import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_legacy_snapshots(apps, schema_editor):
    """Create one legacy snapshot per company for any existing aging records."""
    AgingSnapshot = apps.get_model('aging', 'AgingSnapshot')
    AgingReceivable = apps.get_model('aging', 'AgingReceivable')
    db_alias = schema_editor.connection.alias

    company_ids = (
        AgingReceivable.objects.using(db_alias)
        .values_list('company_id', flat=True)
        .distinct()
    )
    for company_id in company_ids:
        snapshot = AgingSnapshot.objects.using(db_alias).create(
            company_id=company_id,
            source_file='legacy_import',
        )
        AgingReceivable.objects.using(db_alias).filter(
            company_id=company_id
        ).update(snapshot_id=snapshot.id)


def reverse_legacy_snapshots(apps, schema_editor):
    AgingSnapshot = apps.get_model('aging', 'AgingSnapshot')
    db_alias = schema_editor.connection.alias
    AgingSnapshot.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):
    # Must run outside a single transaction so PostgreSQL can alter the table
    # after the RunPython data-migration step.
    atomic = False

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('aging', '0003_remove_report_date'),
    ]

    operations = [
        # 1. Create AgingSnapshot table
        migrations.CreateModel(
            name='AgingSnapshot',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('report_date', models.DateField(
                    blank=True, null=True, verbose_name='Report Date',
                )),
                ('source_file', models.CharField(
                    blank=True, max_length=500, verbose_name='Source File',
                )),
                ('uploaded_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='Uploaded At',
                )),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='aging_snapshots',
                    to='companies.company',
                    verbose_name='Company',
                )),
                ('uploaded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aging_snapshots',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Uploaded By',
                )),
            ],
            options={
                'verbose_name': 'Aging Snapshot',
                'verbose_name_plural': 'Aging Snapshots',
                'db_table': 'aging_snapshot',
                'ordering': ['-uploaded_at'],
            },
        ),

        # 2. Add nullable snapshot FK to AgingReceivable
        migrations.AddField(
            model_name='agingreceivable',
            name='snapshot',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='lines',
                to='aging.agingsnapshot',
                verbose_name='Snapshot',
            ),
        ),

        # 3. Populate snapshot FK for all existing records
        migrations.RunPython(create_legacy_snapshots, reverse_legacy_snapshots),

        # 4. Make snapshot NOT NULL
        migrations.AlterField(
            model_name='agingreceivable',
            name='snapshot',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='lines',
                to='aging.agingsnapshot',
                verbose_name='Snapshot',
            ),
        ),

        # 5. Remove unique_together constraint
        migrations.AlterUniqueTogether(
            name='agingreceivable',
            unique_together=set(),
        ),
    ]
