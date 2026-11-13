"""Admin configuration for live sessions."""

from django.contrib import admin
from .models import LiveSession


@admin.register(LiveSession)
class LiveSessionAdmin(admin.ModelAdmin):
    """Admin for LiveSession model."""

    list_display = ('id', 'connection', 'started_by', 'active', 'started_at', 'ended_at')
    list_filter = ('active',)
    search_fields = ('id', 'connection__user_a__email', 'connection__user_b__email')
    ordering = ('-started_at',)
