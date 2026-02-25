from rest_framework import serializers
from .models import Customer


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = Customer
        fields = [
            "id", "customer_name", "account_code",
            "area_code", "phone", "email",
        ]
        read_only_fields = fields


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Full profile with computed stats."""

    movement_count = serializers.SerializerMethodField()
    latest_aging_total = serializers.SerializerMethodField()
    latest_aging_risk = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "company", "customer_name", "account_code",
            "address", "area_code", "phone", "email",
            "movement_count", "latest_aging_total", "latest_aging_risk",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_movement_count(self, obj):
        return obj.movements.count()

    def get_latest_aging_total(self, obj):
        latest = obj.aging_records.order_by("-report_date").first()
        return float(latest.total) if latest else None

    def get_latest_aging_risk(self, obj):
        latest = obj.aging_records.order_by("-report_date").first()
        return latest.risk_score if latest else None


class CustomerWriteSerializer(serializers.ModelSerializer):
    """Write serializer for create/update (manager / admin only)."""

    class Meta:
        model = Customer
        fields = [
            "customer_name", "account_code",
            "address", "area_code", "phone", "email",
        ]

    def validate_customer_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Customer name cannot be empty.")
        return value

    def validate_account_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Account code cannot be empty.")
        company = self.context["request"].user.company
        qs = Customer.objects.filter(company=company, account_code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Account code '{value}' is already used in your company."
            )
        return value
