from rest_framework import serializers
from .models import Product


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = Product
        fields = [
            "id", "product_code", "lab_code",
            "product_name", "category",
        ]
        read_only_fields = fields


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full serializer with aggregated stats."""

    movement_count = serializers.SerializerMethodField()
    latest_snapshot_date = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "company", "product_code", "lab_code",
            "product_name", "category",
            "movement_count", "latest_snapshot_date", "total_stock",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_movement_count(self, obj):
        return obj.movements.count()

    def get_latest_snapshot_date(self, obj):
        snap = obj.inventory_snapshots.order_by("-snapshot_date").first()
        return snap.snapshot_date if snap else None

    def get_total_stock(self, obj):
        snap = obj.inventory_snapshots.order_by("-snapshot_date").first()
        return float(snap.total_qty) if snap else None


class ProductWriteSerializer(serializers.ModelSerializer):
    """Write serializer for create/update operations (admin only)."""

    class Meta:
        model = Product
        fields = ["product_code", "lab_code", "product_name", "category"]

    def validate_product_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Product code cannot be empty.")
        company = self.context["request"].user.company
        qs = Product.objects.filter(company=company, product_code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Product code '{value}' already exists in your company."
            )
        return value
