"""Field models for CLEAR - Camera management."""

import secrets
from django.db import models


def generate_id():
    """Generate a nanoid-like ID."""
    return secrets.token_urlsafe(16)[:21]


def generate_token():
    """Generate a camera access token."""
    return secrets.token_urlsafe(32)


class Camera(models.Model):
    """Camera registration for field capture."""

    SOURCE_CHOICES = [
        ('browser', 'Browser'),
        ('rtsp', 'RTSP'),
    ]

    END_CHOICES = [
        ('none', 'None'),
        ('end_a', 'End A'),
        ('end_b', 'End B'),
    ]

    COURT_MODE_CHOICES = [
        ('singles', 'Singles'),
        ('doubles', 'Doubles'),
    ]

    CALIB_METHOD_CHOICES = [
        ('manual', 'Manual'),
        ('auto', 'Auto'),
        ('segmentation', 'Segmentation'),
    ]

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    name = models.CharField(max_length=80)
    token = models.CharField(max_length=64, default=generate_token, unique=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='browser')
    rtsp_url = models.CharField(max_length=500, blank=True)
    end = models.CharField(max_length=10, choices=END_CHOICES, default='none')
    court_mode = models.CharField(max_length=10, choices=COURT_MODE_CHOICES, default='singles')
    calib_method = models.CharField(max_length=20, choices=CALIB_METHOD_CHOICES, default='manual')

    # Runtime state (not persisted in traditional DB, handled by manager)
    active = models.BooleanField(default=False)
    online = models.BooleanField(default=False)

    # Overlay settings
    overlays = models.JSONField(default=dict, blank=True)

    # Detector settings
    detector = models.JSONField(default=dict, blank=True)

    # Calibration data
    calibration_data = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cameras'
        verbose_name = 'Camera'
        verbose_name_plural = 'Cameras'

    def __str__(self):
        return self.name


class Recording(models.Model):
    """Recording session for field capture."""

    id = models.CharField(max_length=32, primary_key=True, default=generate_id)
    name = models.CharField(max_length=255, blank=True)
    cameras = models.ManyToManyField(Camera, related_name='recordings')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    files = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'recordings'
        verbose_name = 'Recording'
        verbose_name_plural = 'Recordings'
        ordering = ['-started_at']

    def __str__(self):
        return self.name or f'Recording {self.id}'
