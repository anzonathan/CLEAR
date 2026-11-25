"""Scheduled games between paired users, each filmed by both players' phones."""

import secrets

from django.db import models


def generate_id():
    """Generate a nanoid-like ID."""
    return secrets.token_urlsafe(16)[:21]


class Game(models.Model):
    """A game a pair schedules. Each player films one end of the court with their phone."""

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    COURT_MODE_CHOICES = [('singles', 'Singles'), ('doubles', 'Doubles')]
    ANALYSIS_CHOICES = [
        ('none', 'Not analysed'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    connection = models.ForeignKey(
        'connections.Connection', on_delete=models.CASCADE, related_name='games'
    )
    created_by = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='created_games'
    )
    title = models.CharField(max_length=120, blank=True)
    scheduled_at = models.DateTimeField()
    court_mode = models.CharField(max_length=10, choices=COURT_MODE_CHOICES, default='singles')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='scheduled')

    # Camera slots. Ids point at the field camera registry (src.capture), not a DB table.
    camera_a_id = models.CharField(max_length=32, blank=True)
    camera_a_user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    camera_b_id = models.CharField(max_length=32, blank=True)
    camera_b_user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )

    match_id = models.CharField(max_length=32, blank=True)
    recording_id = models.CharField(max_length=32, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    analysis_status = models.CharField(max_length=10, choices=ANALYSIS_CHOICES, default='none')
    analysis = models.JSONField(null=True, blank=True)
    # Developer-marked time ranges of the recording, analysed/exported individually:
    # [{id, end: 'end_a'|'end_b', label, start_s, end_s}]
    segments = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'games'
        ordering = ['-scheduled_at']

    def __str__(self):
        return self.title or f'Game {self.id}'

    def slot_for(self, user):
        """Return 'end_a', 'end_b' or None for the end this user films."""
        if self.camera_a_user_id == user.id:
            return 'end_a'
        if self.camera_b_user_id == user.id:
            return 'end_b'
        return None


class StreamSettings(models.Model):
    """How phones encode frames for the referee. One row (pk=1), edited in dev tools.

    Phones receive these live over their ingest socket, so a change applies to running
    cameras within seconds. When `adaptive` is on, a phone on a slow link steps down
    fps, then quality, then width, but never below the min_* floors: those floors are
    what keeps the ball big and sharp enough for the detector.
    """

    width = models.PositiveIntegerField(default=1280)
    quality = models.FloatField(default=0.75)
    fps = models.PositiveIntegerField(default=8)

    adaptive = models.BooleanField(default=True)
    min_width = models.PositiveIntegerField(default=960)
    min_quality = models.FloatField(default=0.65)
    min_fps = models.PositiveIntegerField(default=4)

    # YOLO input size. Applied when a game or calibration preview starts.
    yolo_imgsz = models.PositiveIntegerField(default=640)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        db_table = 'stream_settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def to_client(self):
        """The subset a phone needs."""
        return {
            'width': self.width,
            'quality': self.quality,
            'fps': self.fps,
            'adaptive': self.adaptive,
            'min_width': self.min_width,
            'min_quality': self.min_quality,
            'min_fps': self.min_fps,
        }
