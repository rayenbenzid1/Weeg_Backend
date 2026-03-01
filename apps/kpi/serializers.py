"""
apps/kpi/serializers.py
-----------------------
DRF serializers for the Credit KPI API response.
These mirror the TypeScript interfaces in the frontend.
"""
from rest_framework import serializers
from .models import KPISnapshot, RiskyCustomerSnapshot


# ── Nested serializers ────────────────────────────────────────────────────────

class CreditKPIItemSerializer(serializers.Serializer):
    """Single KPI value with metadata."""
    value       = serializers.FloatField()
    label       = serializers.CharField()
    unit        = serializers.CharField()
    description = serializers.CharField()

    # Optional extra fields (present only on some KPIs)
    numerator         = serializers.FloatField(required=False, allow_null=True)
    denominator       = serializers.FloatField(required=False, allow_null=True)
    ca_credit         = serializers.FloatField(required=False, allow_null=True)
    ca_total          = serializers.FloatField(required=False, allow_null=True)
    overdue_amount    = serializers.FloatField(required=False, allow_null=True)
    total_receivables = serializers.FloatField(required=False, allow_null=True)
    recovered_amount  = serializers.FloatField(required=False, allow_null=True)
    total_credit      = serializers.FloatField(required=False, allow_null=True)


class RiskyCustomerSerializer(serializers.Serializer):
    """One entry in the top-N risky customers list."""
    id                 = serializers.CharField()
    account            = serializers.CharField()
    account_code       = serializers.CharField()
    customer_name      = serializers.CharField()
    total              = serializers.FloatField()
    current            = serializers.FloatField()
    overdue_total      = serializers.FloatField()
    risk_score         = serializers.ChoiceField(choices=["low", "medium", "high", "critical"])
    overdue_percentage = serializers.FloatField()
    dmp_days           = serializers.FloatField()
    buckets            = serializers.DictField(child=serializers.FloatField())


class BucketDistributionItemSerializer(serializers.Serializer):
    """Aging bucket with label, amount and percentage."""
    bucket        = serializers.CharField()
    label         = serializers.CharField()
    amount        = serializers.FloatField()
    percentage    = serializers.FloatField()
    midpoint_days = serializers.FloatField()


class SummarySerializer(serializers.Serializer):
    """High-level summary figures."""
    total_customers         = serializers.IntegerField()
    credit_customers        = serializers.IntegerField()
    grand_total_receivables = serializers.FloatField()
    overdue_amount          = serializers.FloatField()
    ca_credit               = serializers.FloatField()
    ca_total                = serializers.FloatField()


class KPIsSerializer(serializers.Serializer):
    """Container for all 5 credit KPIs."""
    taux_clients_credit = CreditKPIItemSerializer()
    taux_credit_total   = CreditKPIItemSerializer()
    taux_impayes        = CreditKPIItemSerializer()
    dmp                 = CreditKPIItemSerializer()
    taux_recouvrement   = CreditKPIItemSerializer()


# ── Main response serializer ──────────────────────────────────────────────────

class CreditKPIResponseSerializer(serializers.Serializer):
    """
    Full API response for GET /api/kpi/credit/
    Mirrors the CreditKPIData TypeScript interface.
    """
    report_date          = serializers.DateField(allow_null=True)
    kpis                 = KPIsSerializer()
    top5_risky_customers = RiskyCustomerSerializer(many=True)
    bucket_distribution  = BucketDistributionItemSerializer(many=True)
    summary              = SummarySerializer()


# ── Model serializers (for admin / caching layer) ─────────────────────────────

class KPISnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = KPISnapshot
        fields = "__all__"


class RiskyCustomerSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RiskyCustomerSnapshot
        fields = "__all__"