"""Live session serializers for CLEAR."""

from rest_framework import serializers
from .models import LiveSession


class LiveSessionSerializer(serializers.ModelSerializer):
    """Serializer for LiveSession model."""

    other_name = serializers.SerializerMethodField()

    class Meta:
        model = LiveSession
        fields = [
            'id', 'connection_id', 'started_by_id', 'other_name',
            'active', 'started_at', 'ended_at'
        ]
        read_only_fields = ['id', 'started_at', 'ended_at']

    def get_other_name(self, obj):
        user = self.context['request'].user
        other = obj.connection.get_other_user(user)
        return other.name


class StartSessionSerializer(serializers.Serializer):
    """Serializer for starting a live session."""

    connectionId = serializers.CharField()


class EndSessionSerializer(serializers.Serializer):
    """Serializer for ending a live session."""

    sessionId = serializers.CharField()
