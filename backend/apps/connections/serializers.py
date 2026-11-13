"""Connection serializers for CLEAR."""

from rest_framework import serializers
from .models import PairCode, Connection
from apps.users.serializers import UserSerializer


class PairCodeSerializer(serializers.ModelSerializer):
    """Serializer for PairCode model."""

    class Meta:
        model = PairCode
        fields = ['code', 'expires_at']
        read_only_fields = ['code', 'expires_at']


class ConnectionSerializer(serializers.ModelSerializer):
    """Serializer for Connection model."""

    other_id = serializers.SerializerMethodField()
    other_name = serializers.SerializerMethodField()
    other_email = serializers.SerializerMethodField()
    other_image = serializers.SerializerMethodField()

    class Meta:
        model = Connection
        fields = [
            'id', 'user_a', 'user_b', 'other_id', 'other_name',
            'other_email', 'other_image', 'active', 'created_at'
        ]

    def get_other_id(self, obj):
        user = self.context['request'].user
        other = obj.get_other_user(user)
        return other.id

    def get_other_name(self, obj):
        user = self.context['request'].user
        other = obj.get_other_user(user)
        return other.name

    def get_other_email(self, obj):
        user = self.context['request'].user
        other = obj.get_other_user(user)
        return other.email

    def get_other_image(self, obj):
        user = self.context['request'].user
        other = obj.get_other_user(user)
        return other.image


class ConnectionDetailSerializer(ConnectionSerializer):
    """Serializer for Connection with videos."""

    videos = serializers.SerializerMethodField()

    class Meta(ConnectionSerializer.Meta):
        fields = ConnectionSerializer.Meta.fields + ['videos']

    def get_videos(self, obj):
        from apps.videos.serializers import SharedVideoSerializer
        videos = obj.shared_videos.all().order_by('-created_at')
        return SharedVideoSerializer(videos, many=True).data


class JoinCodeSerializer(serializers.Serializer):
    """Serializer for joining via pair code."""

    code = serializers.CharField(max_length=6)
