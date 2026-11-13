"""Live session models for CLEAR."""

import secrets
from django.db import models


def generate_id():
    """Generate a nanoid-like ID."""
    return secrets.token_urlsafe(16)[:21]


class LiveSession(models.Model):
    """Live video session between connected users."""

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    connection = models.ForeignKey(
        'connections.Connection',
        on_delete=models.CASCADE,
        related_name='live_sessions'
    )
    started_by = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='started_sessions'
    )
    active = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'live_sessions'
        verbose_name = 'Live Session'
        verbose_name_plural = 'Live Sessions'
        ordering = ['-started_at']

    def __str__(self):
        return f'Session {self.id} ({self.connection})'
