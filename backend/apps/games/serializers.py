"""Game serializers."""

from django.utils import timezone
from rest_framework import serializers

from . import services
from .models import Game


def _user_brief(user):
    if user is None:
        return None
    return {'id': str(user.id), 'name': user.name or user.email, 'email': user.email}


class GameSerializer(serializers.ModelSerializer):
    """Game as a participant sees it. Includes the requester's own camera token only."""

    partner = serializers.SerializerMethodField()
    ends = serializers.SerializerMethodField()
    my_end = serializers.SerializerMethodField()
    my_camera = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            'id', 'title', 'connection', 'scheduled_at', 'court_mode', 'status',
            'partner', 'ends', 'my_end', 'my_camera',
            'started_at', 'ended_at', 'analysis_status', 'analysis', 'created_at',
        ]

    def _me(self):
        return self.context['request'].user

    def get_partner(self, obj):
        return _user_brief(obj.connection.get_other_user(self._me()))

    def get_ends(self, obj):
        return {
            'end_a': {'user': _user_brief(obj.camera_a_user), 'camera': services.camera_state(obj.camera_a_id)},
            'end_b': {'user': _user_brief(obj.camera_b_user), 'camera': services.camera_state(obj.camera_b_id)},
        }

    def get_my_end(self, obj):
        return obj.slot_for(self._me())

    def get_my_camera(self, obj):
        slot = obj.slot_for(self._me())
        if slot is None:
            return None
        cam_id = obj.camera_a_id if slot == 'end_a' else obj.camera_b_id
        return {'id': cam_id, 'token': services.camera_token(cam_id)}


class DevGameSerializer(serializers.ModelSerializer):
    """Game as a developer sees it: both players, raw ids, no camera tokens."""

    players = serializers.SerializerMethodField()
    ends = serializers.SerializerMethodField()
    recorded = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            'id', 'title', 'scheduled_at', 'court_mode', 'status', 'players', 'ends',
            'match_id', 'recording_id', 'recorded', 'started_at', 'ended_at',
            'analysis_status', 'analysis', 'created_at',
        ]

    def get_players(self, obj):
        return [_user_brief(obj.connection.user_a), _user_brief(obj.connection.user_b)]

    def get_ends(self, obj):
        return {
            'end_a': {'user': _user_brief(obj.camera_a_user), 'camera': services.camera_state(obj.camera_a_id)},
            'end_b': {'user': _user_brief(obj.camera_b_user), 'camera': services.camera_state(obj.camera_b_id)},
        }

    def get_recorded(self, obj):
        return len(services.recording_files(obj)) if obj.status == 'completed' else 0


class GameCreateSerializer(serializers.Serializer):
    connection_id = serializers.CharField()
    scheduled_at = serializers.DateTimeField()
    court_mode = serializers.ChoiceField(choices=['singles', 'doubles'], default='singles')
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_scheduled_at(self, value):
        if value < timezone.now() - timezone.timedelta(minutes=5):
            raise serializers.ValidationError('Pick a time in the future.')
        return value


class GameUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['title', 'scheduled_at', 'court_mode']


class StreamSettingsSerializer(serializers.ModelSerializer):
    updated_by = serializers.SerializerMethodField()

    class Meta:
        from .models import StreamSettings

        model = StreamSettings
        fields = [
            'width', 'quality', 'fps', 'adaptive', 'min_width', 'min_quality', 'min_fps',
            'yolo_imgsz', 'updated_at', 'updated_by',
        ]
        read_only_fields = ['updated_at', 'updated_by']
        extra_kwargs = {
            'width': {'min_value': 320, 'max_value': 1920},
            'min_width': {'min_value': 320, 'max_value': 1920},
            'quality': {'min_value': 0.3, 'max_value': 0.95},
            'min_quality': {'min_value': 0.3, 'max_value': 0.95},
            'fps': {'min_value': 1, 'max_value': 20},
            'min_fps': {'min_value': 1, 'max_value': 20},
            'yolo_imgsz': {'min_value': 320, 'max_value': 1920},
        }

    def get_updated_by(self, obj):
        return obj.updated_by.name if obj.updated_by else None

    def validate(self, data):
        inst = self.instance
        get = lambda k: data.get(k, getattr(inst, k) if inst else None)  # noqa: E731
        if get('min_width') > get('width'):
            raise serializers.ValidationError({'min_width': 'Floor cannot be above the resolution.'})
        if get('min_quality') > get('quality'):
            raise serializers.ValidationError({'min_quality': 'Floor cannot be above the quality.'})
        if get('min_fps') > get('fps'):
            raise serializers.ValidationError({'min_fps': 'Floor cannot be above the frame rate.'})
        if get('yolo_imgsz') % 32:
            raise serializers.ValidationError({'yolo_imgsz': 'Must be a multiple of 32.'})
        return data
