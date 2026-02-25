from rest_framework import serializers
from .models import MaterialMovement


class MovementListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views and cross-app references
    (used by CustomerMovementsView, ProductMovementsView, etc.).
    """

    movement_type_display = serializers.CharField(
        source="get_movement_type_display",
        read_only=True,
    )

    class Meta:
        model = MaterialMovement
        fields = [
            "id",
            "material_code", "material_name",
            "movement_date", "movement_type", "movement_type_display",
            "qty_in", "qty_out",
            "total_in", "total_out",
            "balance_price",
            "branch_name", "customer_name",
        ]
        read_only_fields = fields


class MovementDetailSerializer(serializers.ModelSerializer):
    """
    Full serializer for the movement detail view.
    Includes all FK-resolved fields and their raw counterparts.
    """

    movement_type_display = serializers.CharField(
        source="get_movement_type_display",
        read_only=True,
    )
    product_code = serializers.CharField(
        source="product.product_code",
        read_only=True,
        allow_null=True,
    )
    product_name_resolved = serializers.CharField(
        source="product.product_name",
        read_only=True,
        allow_null=True,
    )
    branch_name_resolved = serializers.CharField(
        source="branch.name",
        read_only=True,
        allow_null=True,
    )
    customer_name_resolved = serializers.CharField(
        source="customer.customer_name",
        read_only=True,
        allow_null=True,
    )
    customer_account_code = serializers.CharField(
        source="customer.account_code",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = MaterialMovement
        fields = [
            "id", "company",
            # Product
            "product", "product_code", "product_name_resolved",
            "category", "material_code", "lab_code", "material_name",
            # Movement
            "movement_date", "movement_type", "movement_type_display", "movement_type_raw",
            # Quantities
            "qty_in", "price_in", "total_in",
            "qty_out", "price_out", "total_out",
            "balance_price",
            # Branch
            "branch", "branch_name", "branch_name_resolved",
            # Customer
            "customer", "customer_name", "customer_name_resolved", "customer_account_code",
            # Metadata
            "created_at",
        ]
        read_only_fields = fields


class MovementSummarySerializer(serializers.Serializer):
    """Serializer for the monthly summary aggregation."""

    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_label = serializers.CharField()
    total_sales = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_purchases = serializers.DecimalField(max_digits=18, decimal_places=2)
    sales_count = serializers.IntegerField()
    purchases_count = serializers.IntegerField()
