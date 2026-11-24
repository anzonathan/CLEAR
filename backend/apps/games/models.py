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
