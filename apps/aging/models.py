import uuid
from django.db import models
from django.db.models import Sum


class AgingReceivable(models.Model):
    """
    Represents a customer aging receivables record imported from the Excel file
    (اعمار_الذمم_2025).

    Each row corresponds to one customer account with their outstanding
    balances broken down into aging buckets (current, 1-30 days, 31-60 days, ...).

    The total field is computed from the raw data to avoid reliance on
    Excel formula values.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="aging_receivables",
        verbose_name="Company",
    )

    # Optional FK to Customer — linked if account_code matches
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

    # Snapshot date for this aging report
    report_date = models.DateField(
        verbose_name="Report Date",
        help_text="Date of the aging report snapshot.",
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
        unique_together = [("company", "account_code", "report_date")]

    def __str__(self):
        return f"{self.account} — {self.total} LYD ({self.report_date})"

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
