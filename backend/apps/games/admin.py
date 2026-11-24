from django.contrib import admin

from .models import Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'connection', 'scheduled_at', 'status', 'analysis_status')
    list_filter = ('status', 'analysis_status', 'court_mode')
