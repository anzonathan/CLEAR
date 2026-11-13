"""Admin configuration for connections."""

from django.contrib import admin
from .models import PairCode, Connection


@admin.register(PairCode)
class PairCodeAdmin(admin.ModelAdmin):
    """Admin for PairCode model."""

    list_display = ('code', 'creator', 'expires_at', 'used', 'used_by', 'created_at')
    list_filter = ('used',)
    search_fields = ('code', 'creator__email')
    ordering = ('-created_at',)


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    """Admin for Connection model."""

    list_display = ('id', 'user_a', 'user_b', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('user_a__email', 'user_b__email')
    ordering = ('-created_at',)
