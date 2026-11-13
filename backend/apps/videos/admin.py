"""Admin configuration for videos."""

from django.contrib import admin
from .models import SharedVideo


@admin.register(SharedVideo)
class SharedVideoAdmin(admin.ModelAdmin):
    """Admin for SharedVideo model."""

    list_display = ('file_name', 'uploader', 'connection', 'type', 'processed', 'created_at')
    list_filter = ('type', 'processed')
    search_fields = ('file_name', 'uploader__email')
    ordering = ('-created_at',)
