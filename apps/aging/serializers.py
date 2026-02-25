from rest_framework import serializers
from .models import AgingReceivable


class AgingReceivableSerializer(serializers.ModelSerializer):
    """Full serializer including all aging buckets and computed properties."""

    risk_score = serializers.SerializerMethodField()
    overdue_total = serializers.SerializerMethodField()

    customer_name = serializers.CharField(
        source="customer.customer_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AgingReceivable
        fields = [
            "id", "report_date",
            "customer", "customer_name",
            "account", "account_code",
            # Buckets
            "current", "d1_30", "d31_60", "d61_90", "d91_120",
            "d121_150", "d151_180", "d181_210", "d211_240",
            "d241_270", "d271_300", "d301_330", "over_330",
            # Computed
            "total", "overdue_total", "risk_score",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_risk_score(self, obj):
        return obj.risk_score

    def get_overdue_total(self, obj):
        return float(obj.overdue_total)


class AgingListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    risk_score = serializers.SerializerMethodField()
    customer_name = serializers.CharField(
        source="customer.customer_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AgingReceivable
        fields = [
            "id", "report_date",
            "account_code", "account", "customer_name",
            "current", "d1_30", "d31_60",
            "total", "risk_score",
        ]
        read_only_fields = fields

    def get_risk_score(self, obj):
        return obj.risk_score


class AgingDistributionSerializer(serializers.Serializer):
    """Serializer for bucket distribution aggregation."""

    bucket = serializers.CharField()
    label = serializers.CharField()
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    percentage = serializers.FloatField()
