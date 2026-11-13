"""Field serializers for CLEAR."""

from rest_framework import serializers
from .models import Camera, Recording


class CameraSerializer(serializers.ModelSerializer):
    """Serializer for Camera model."""

    class Meta:
        model = Camera
        fields = [
            'id', 'name', 'token', 'source', 'rtsp_url', 'end',
            'court_mode', 'calib_method', 'active', 'online',
            'overlays', 'detector', 'calibration_data',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'token', 'created_at', 'updated_at']


class CameraCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a camera."""

    class Meta:
        model = Camera
        fields = ['name', 'source', 'rtsp_url', 'end']


class CameraUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a camera."""

    class Meta:
        model = Camera
        fields = [
            'name', 'source', 'rtsp_url', 'court_mode',
            'calib_method', 'end', 'overlays', 'detector'
        ]
        extra_kwargs = {field: {'required': False} for field in fields}


class RecordingSerializer(serializers.ModelSerializer):
    """Serializer for Recording model."""

    class Meta:
        model = Recording
        fields = [
            'id', 'name', 'started_at', 'ended_at',
            'duration_seconds', 'files'
        ]
        read_only_fields = ['id', 'started_at', 'ended_at', 'duration_seconds']


class CalibrationRequestSerializer(serializers.Serializer):
    """Serializer for calibration request."""

    anchors_px = serializers.DictField(child=serializers.ListField(child=serializers.FloatField()))
    method = serializers.ChoiceField(choices=['manual', 'auto', 'segmentation'], default='manual')


class MatchRequestSerializer(serializers.Serializer):
    """Serializer for match request."""

    camera_a_id = serializers.CharField()
    camera_b_id = serializers.CharField()


class RecordStartSerializer(serializers.Serializer):
    """Serializer for starting a recording."""

    camera_ids = serializers.ListField(child=serializers.CharField())
    name = serializers.CharField(required=False, allow_blank=True)
