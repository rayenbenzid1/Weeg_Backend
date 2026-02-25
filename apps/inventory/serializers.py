from rest_framework import serializers
from .models import InventorySnapshot


class InventorySnapshotSerializer(serializers.ModelSerializer):
    """Full snapshot serializer with computed totals."""

    product_code = serializers.CharField(source="product.product_code", read_only=True)
    product_name = serializers.CharField(source="product.product_name", read_only=True)
    category = serializers.CharField(source="product.category", read_only=True)
    total_branches_value = serializers.SerializerMethodField()

    class Meta:
        model = InventorySnapshot
        fields = [
            "id", "snapshot_date",
            "product", "product_code", "product_name", "category",
            # Quantities per branch
            "qty_alkarimia", "qty_benghazi", "qty_mazraa",
            "qty_dahmani", "qty_janzour", "qty_misrata",
            # Values per branch
            "value_alkarimia", "value_mazraa",
            "value_dahmani", "value_janzour", "value_misrata",
            # Totals
            "total_qty", "cost_price", "total_value",
            "total_branches_value",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_total_branches_value(self, obj):
        return float(obj.total_branches_value)


class InventorySnapshotListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    product_code = serializers.CharField(source="product.product_code", read_only=True)
    product_name = serializers.CharField(source="product.product_name", read_only=True)
    category = serializers.CharField(source="product.category", read_only=True)

    class Meta:
        model = InventorySnapshot
        fields = [
            "id", "snapshot_date",
            "product_code", "product_name", "category",
            "total_qty", "cost_price", "total_value",
        ]
        read_only_fields = fields


class BranchSummarySerializer(serializers.Serializer):
    """Serializer for cross-branch aggregated totals."""

    branch = serializers.CharField()
    total_qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_value = serializers.DecimalField(max_digits=18, decimal_places=4)
