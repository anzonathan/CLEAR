"""Video serializers for CLEAR."""

from rest_framework import serializers
from .models import SharedVideo


class SharedVideoSerializer(serializers.ModelSerializer):
    """Serializer for SharedVideo model."""

    uploader_name = serializers.CharField(source='uploader.name', read_only=True)

    class Meta:
        model = SharedVideo
        fields = [
            'id', 'uploader_id', 'uploader_name', 'connection_id',
            'file_path', 'file_name', 'file_size', 'mime_type',
            'type', 'thumbnail_path', 'duration_seconds',
            'processed', 'detection_results', 'created_at'
        ]
        read_only_fields = ['id', 'uploader_id', 'uploader_name', 'created_at']


class VideoUploadSerializer(serializers.Serializer):
    """Serializer for video upload."""

    connection_id = serializers.CharField()
    file = serializers.FileField()
    type = serializers.ChoiceField(choices=['recorded', 'live'], default='recorded')
