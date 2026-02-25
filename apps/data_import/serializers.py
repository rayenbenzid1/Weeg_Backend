# apps/data_import/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import ImportLog


class ImportUploadSerializer(serializers.Serializer):
    """
    Serializer for file upload in /api/import/upload/
    Handles multipart form data with file and optional metadata.
    """
    file = serializers.FileField(
        required=True,
        allow_empty_file=False,
        help_text="Excel file (.xlsx or .xls) to import"
    )
    file_type = serializers.ChoiceField(
        choices=ImportLog.FileType.choices,
        required=False,
        allow_blank=True,
        help_text="Optional: force file type instead of auto-detection"
    )
    snapshot_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Snapshot/reference date (mainly for inventory/aging)"
    )
    report_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Report generation date (mainly for aging receivables)"
    )

    def validate_file(self, value):
        """
        Basic file validation before processing.
        """
        if not value.name.lower().endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError(
                "Only .xlsx and .xls files are supported."
            )
        if value.size == 0:
            raise serializers.ValidationError(
                "Uploaded file is empty."
            )
        return value


class ImportLogSerializer(serializers.ModelSerializer):
    """
    Main serializer for ImportLog entries.
    Used in list, detail, and upload response.
    """
    imported_by_username = serializers.CharField(
        source='imported_by.username',
        read_only=True,
        allow_null=True
    )
    imported_by_full_name = serializers.CharField(
        source='imported_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    company_name = serializers.CharField(
        source='company.name',
        read_only=True
    )
    duration = serializers.SerializerMethodField(
        help_text="Time taken to complete the import (if finished)"
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    file_type_display = serializers.CharField(
        source='get_file_type_display',
        read_only=True
    )

    class Meta:
        model = ImportLog
        fields = [
            'id',
            'company',
            'company_name',
            'imported_by',
            'imported_by_username',
            'imported_by_full_name',
            'file_type',
            'file_type_display',
            'original_filename',
            'status',
            'status_display',
            'row_count',
            'success_count',
            'error_count',
            'error_details',
            'import_context',
            'started_at',
            'completed_at',
            'duration',
        ]
        read_only_fields = [
            'id', 'company', 'imported_by', 'started_at', 'completed_at',
            'row_count', 'success_count', 'error_count', 'error_details',
            'status', 'file_type', 'original_filename',
        ]

    def get_duration(self, obj):
        if obj.completed_at and obj.started_at:
            delta = obj.completed_at - obj.started_at
            total_seconds = int(delta.total_seconds())
            if total_seconds < 60:
                return f"{total_seconds} seconds"
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        return None


class ImportLogMinimalSerializer(serializers.ModelSerializer):
    """
    Lighter version used when returning many logs (list view)
    to reduce payload size.
    """
    class Meta:
        model = ImportLog
        fields = [
            'id',
            'file_type',
            'original_filename',
            'status',
            'row_count',
            'success_count',
            'error_count',
            'started_at',
            'completed_at',
        ]