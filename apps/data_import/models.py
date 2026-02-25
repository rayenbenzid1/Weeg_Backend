import uuid
from django.db import models
from django.conf import settings


class ImportLog(models.Model):
    """
    Tracks every Excel import operation performed on the platform.

    An ImportLog is created at the start of each import, then updated
    as processing proceeds. If the import fails partway through, the
    partial results are rolled back and the error is stored here.
    """

    class FileType(models.TextChoices):
        BRANCHES = "branches", "Branches"
        CUSTOMERS = "customers", "Customers"
        MOVEMENTS = "movements", "Material Movements"
        INVENTORY = "inventory", "Inventory Snapshot"
        AGING = "aging", "Aging Receivables"

    class ImportStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="import_logs",
        verbose_name="Company",
    )

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="import_logs",
        verbose_name="Imported By",
    )

    file_type = models.CharField(
        max_length=30,
        choices=FileType.choices,
        verbose_name="File Type",
    )

    original_filename = models.CharField(
        max_length=500,
        verbose_name="Original Filename",
    )

    status = models.CharField(
        max_length=20,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
        verbose_name="Status",
    )

    row_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Rows Processed",
    )

    success_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Rows Successfully Imported",
    )

    error_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Rows With Errors",
    )

    error_details = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Error Details",
        help_text="List of {row, error} dicts for failed rows.",
    )

    # Extra context stored during import (e.g. snapshot_date for inventory)
    import_context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Import Context",
    )

    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Started At")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completed At")

    class Meta:
        db_table = "data_import_log"
        verbose_name = "Import Log"
        verbose_name_plural = "Import Logs"
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"[{self.file_type}] {self.original_filename} "
            f"— {self.status} ({self.success_count}/{self.row_count} rows)"
        )
