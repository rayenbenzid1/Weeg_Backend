import uuid
from django.conf import settings
from django.db import models
from django.db.models import Sum


class AgingSnapshot(models.Model):
    """
    One import-session record per uploaded aging Excel file.

    All AgingReceivable lines produced by a single import are linked here.
    Deleting a snapshot cascades to all its lines — full rollback in one DELETE.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="aging_snapshots",
        verbose_name="Company",
    )

    aging_year = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Aging Year",
        help_text="4-digit fiscal year extracted from the uploaded filename.",
    )

    report_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Report Date",
    )

    source_file = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Source File",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aging_snapshots",
        verbose_name="Uploaded By",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Uploaded At",
    )

    class Meta:
        db_table = "aging_snapshot"
        ordering = ["-uploaded_at"]
        verbose_name = "Aging Snapshot"
        verbose_name_plural = "Aging Snapshots"

    def __str__(self):
        label = str(self.report_date or self.uploaded_at.date())
        return f"Aging {label} — {self.company}"


class AgingReceivable(models.Model):
    """
    One customer account row from an aging Excel report.

    Each instance belongs to one AgingSnapshot session.
    Deleting the snapshot cascades to all its lines.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    snapshot = models.ForeignKey(
        AgingSnapshot,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Snapshot",
    )

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="aging_receivables",
        verbose_name="Company",
        help_text="Denormalized from snapshot for efficient filtering.",
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aging_records",
        verbose_name="Customer",
    )

    # Raw account string from Excel (e.g. "1141001 - عملاء قطاعي / نقدي")
    account = models.CharField(
        max_length=500,
        verbose_name="Account",
        help_text="Full account label from the Excel file.",
    )

    # Account code extracted from the account string
    account_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Account Code",
        db_index=True,
    )

    # ── Aging buckets (all in LYD) ────────────────────────────────────────────

    current = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="Current (not yet due)",
    )
    d1_30 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="1–30 Days",
    )
    d31_60 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="31–60 Days",
    )
    d61_90 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="61–90 Days",
    )
    d91_120 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="91–120 Days",
    )
    d121_150 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="121–150 Days",
    )
    d151_180 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="151–180 Days",
    )
    d181_210 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="181–210 Days",
    )
    d211_240 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="211–240 Days",
    )
    d241_270 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="241–270 Days",
    )
    d271_300 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="271–300 Days",
    )
    d301_330 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="301–330 Days",
    )
    over_330 = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="Over 330 Days",
    )

    # Computed total (sum of all buckets)
    total = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        verbose_name="Total Balance (LYD)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "aging_receivable"
        verbose_name = "Aging Receivable"
        verbose_name_plural = "Aging Receivables"
        ordering = ["-total", "account"]

    def __str__(self):
        return f"{self.account} — {self.total} LYD"

    def compute_total(self):
        """Recalculate total from all aging buckets."""
        return (
            self.current + self.d1_30 + self.d31_60 + self.d61_90 +
            self.d91_120 + self.d121_150 + self.d151_180 + self.d181_210 +
            self.d211_240 + self.d241_270 + self.d271_300 + self.d301_330 +
            self.over_330
        )

    @property
    def overdue_total(self):
        """Sum of all buckets beyond 60 days."""
        return (
            self.d61_90 + self.d91_120 + self.d121_150 + self.d151_180 +
            self.d181_210 + self.d211_240 + self.d241_270 + self.d271_300 +
            self.d301_330 + self.over_330
        )

    @property
    def risk_score(self) -> str:
        """
        Simple risk classification based on overdue amounts.
        Returns: 'low' | 'medium' | 'high' | 'critical'
        """
        overdue = float(self.overdue_total)
        total = float(self.total)
        if total == 0:
            return "low"
        ratio = overdue / total
        if ratio < 0.2:
            return "low"
        if ratio < 0.5:
            return "medium"
        if ratio < 0.75:
            return "high"
        return "critical"
