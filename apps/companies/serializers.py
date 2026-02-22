from rest_framework import serializers
from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "industry", "phone", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class CompanyMinimalSerializer(serializers.ModelSerializer):
    """Minimal representation used in nested serializers."""
    class Meta:
        model = Company
        fields = ["id", "name"]
