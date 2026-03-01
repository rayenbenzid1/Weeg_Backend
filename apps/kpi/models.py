"""
apps/kpi/models.py
------------------
Models for the KPI application.
The credit KPIs are computed on-the-fly from the Aging and Movement tables.
This model caches the last computation to speed up repeated requests.
"""
from django.db import models
from django.utils import timezone


class KPISnapshot(models.Model):
    """
    Cached snapshot of all computed KPI values.
    One row per report_date; refreshed automatically by the view when stale (> 1 hour).
    """

    RISK_CHOICES = [
        ("low",      "Faible"),
        ("medium",   "Moyen"),
        ("high",     "Élevé"),
        ("critical", "Critique"),
    ]

    # When was this snapshot calculated?
    computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    # The aging report date this snapshot is based on (None = latest available)
    report_date = models.DateField(null=True, blank=True, db_index=True)

    # ── KPI values ──────────────────────────────────────────────────────────
    taux_clients_credit = models.FloatField(default=0.0)
    taux_credit_total   = models.FloatField(default=0.0)
    taux_impayes        = models.FloatField(default=0.0)
    dmp                 = models.FloatField(default=0.0, verbose_name="Délai Moyen de Paiement (jours)")
    taux_recouvrement   = models.FloatField(default=0.0)

    # ── Summary figures ──────────────────────────────────────────────────────
    total_customers           = models.IntegerField(default=0)
    credit_customers          = models.IntegerField(default=0)
    grand_total_receivables   = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    overdue_amount            = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    ca_credit                 = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    ca_total                  = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    class Meta:
        ordering = ["-computed_at"]
        verbose_name = "KPI Snapshot"
        verbose_name_plural = "KPI Snapshots"

    def __str__(self):
        return f"KPI Snapshot — {self.report_date or 'latest'} (computed {self.computed_at:%Y-%m-%d %H:%M})"

    def is_stale(self, ttl_seconds: int = 3600) -> bool:
        """Return True if this snapshot is older than `ttl_seconds`."""
        age = (timezone.now() - self.computed_at).total_seconds()
        return age > ttl_seconds


class RiskyCustomerSnapshot(models.Model):
    """
    Top-N risky customers stored alongside a KPI snapshot.
    """

    RISK_CHOICES = KPISnapshot.RISK_CHOICES

    snapshot     = models.ForeignKey(
        KPISnapshot,
        on_delete=models.CASCADE,
        related_name="risky_customers",
    )
    rank         = models.PositiveSmallIntegerField()

    account_code  = models.CharField(max_length=50)
    customer_name = models.CharField(max_length=255, blank=True)

    total         = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    current       = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    overdue_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    risk_score         = models.CharField(max_length=10, choices=RISK_CHOICES, default="low")
    overdue_percentage = models.FloatField(default=0.0)
    dmp_days           = models.FloatField(default=0.0)

    # Aging buckets stored as JSON
    buckets = models.JSONField(default=dict)

    class Meta:
        ordering = ["snapshot", "rank"]
        verbose_name = "Risky Customer Snapshot"
        verbose_name_plural = "Risky Customer Snapshots"

    def __str__(self):
        return f"#{self.rank} {self.customer_name or self.account_code} ({self.risk_score})"