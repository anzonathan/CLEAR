"""Admin configuration for field."""

from django.contrib import admin
from .models import Camera, Recording


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    """Admin for Camera model."""

    list_display = ('name', 'source', 'end', 'active', 'online', 'created_at')
    list_filter = ('source', 'end', 'active', 'online')
    search_fields = ('name', 'id')
    ordering = ('-created_at',)


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    """Admin for Recording model."""

    list_display = ('id', 'name', 'started_at', 'ended_at', 'duration_seconds')
    search_fields = ('name', 'id')
    ordering = ('-started_at',)
