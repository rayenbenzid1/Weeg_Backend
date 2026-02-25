# apps/transactions/serializers.py
from rest_framework import serializers
from .models import MaterialMovement


class MaterialMovementSerializer(serializers.ModelSerializer):
    """
    Serializer principal pour les mouvements de matières (transactions).
    """
    movement_type_display = serializers.CharField(
        source='get_movement_type_display',
        read_only=True
    )
    company_name = serializers.CharField(
        source='company.name',
        read_only=True
    )
    product_name = serializers.CharField(
        source='product.name',
        read_only=True,
        allow_null=True
    )
    branch_name_resolved = serializers.CharField(
        source='branch.name',
        read_only=True,
        allow_null=True
    )
    customer_name_resolved = serializers.CharField(
        source='customer.name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = MaterialMovement
        fields = [
            'id',
            'company',
            'company_name',
            'product',
            'product_name',
            'category',
            'material_code',
            'lab_code',
            'material_name',
            'movement_date',
            'movement_type',
            'movement_type_display',
            'movement_type_raw',
            'qty_in',
            'price_in',
            'total_in',
            'qty_out',
            'price_out',
            'total_out',
            'balance_price',
            'branch',
            'branch_name',
            'branch_name_resolved',
            'customer',
            'customer_name',
            'customer_name_resolved',
            'created_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'company', 'company_name',
            'product_name', 'branch_name_resolved', 'customer_name_resolved',
            'movement_type_display',
        ]


class MaterialMovementMinimalSerializer(serializers.ModelSerializer):
    """
    Version allégée pour les listes (meilleure performance).
    """
    movement_type_display = serializers.CharField(
        source='get_movement_type_display',
        read_only=True
    )

    class Meta:
        model = MaterialMovement
        fields = [
            'id',
            'material_code',
            'material_name',
            'movement_date',
            'movement_type',
            'movement_type_display',
            'qty_in',
            'qty_out',
            'total_in',
            'total_out',
            'balance_price',
        ]