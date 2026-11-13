"""Video models for CLEAR."""

import secrets
from django.db import models


def generate_id():
    """Generate a nanoid-like ID."""
    return secrets.token_urlsafe(16)[:21]


class SharedVideo(models.Model):
    """Shared video between connected users."""

    TYPE_CHOICES = [
        ('recorded', 'Recorded'),
        ('live', 'Live'),
    ]

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    uploader = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='uploaded_videos'
    )
    connection = models.ForeignKey(
        'connections.Connection',
        on_delete=models.CASCADE,
        related_name='shared_videos'
    )
    file_path = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='recorded')
    thumbnail_path = models.CharField(max_length=500, null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    processed = models.BooleanField(default=False)
    detection_results = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shared_videos'
        verbose_name = 'Shared Video'
        verbose_name_plural = 'Shared Videos'
        ordering = ['-created_at']

    def __str__(self):
        return self.file_name
