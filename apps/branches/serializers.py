from rest_framework import serializers
from .models import Branch , BranchAlias  


class BranchSerializer(serializers.ModelSerializer):

    class Meta:
        model = Branch
        fields = [
            "id", "name", "address", "city",
            "phone", "email", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
class BranchAliasSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True, allow_null=True)

    class Meta:
        model  = BranchAlias
        fields = [
            "id", "alias",
            "branch", "branch_name",
            "auto_matched", "created_at",
        ]
        read_only_fields = ["id", "auto_matched", "created_at"]