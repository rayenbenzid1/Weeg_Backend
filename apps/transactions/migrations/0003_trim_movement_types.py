# apps/transactions/migrations/0003_trim_movement_types.py
#
# One-shot data migration: strips leading/trailing whitespace from every
# movement_type value stored in the DB.
#
# Why this is needed
# ──────────────────
# Some Excel files (e.g. حركة_المادة_الشنت.xlsx) contain movement-type cells
# with a trailing U+0020 space — e.g. 'ف بيع ' instead of 'ف بيع'.
# Those rows were imported before the explicit .strip() guard was added to the
# parser, so they reached the DB with the extra space.  Queries that filter by
# the canonical value ('ف بيع') therefore returned 0 rows for the affected
# branch, making that branch vanish from every chart.
#
# This migration fixes all existing rows in one SQL UPDATE; the parser and
# views have been hardened so future imports will never re-introduce the issue.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Must run after the last confirmed transactions migration
        ("transactions", "0002_remove_materialmovement_branch_name"),
    ]

    operations = [
        migrations.RunSQL(
            # ── Forward: trim every movement_type value ──────────────────────
            sql="""
                UPDATE transactions_movement
                SET    movement_type = TRIM(movement_type)
                WHERE  movement_type != TRIM(movement_type);
            """,
            # ── Reverse: no-op (trimming is idempotent / loss-less) ──────────
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]