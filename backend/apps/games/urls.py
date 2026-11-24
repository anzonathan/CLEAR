from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import DevGameViewSet, GameViewSet, StreamLiveView, StreamSettingsView

router = DefaultRouter()
router.register('games', GameViewSet, basename='games')
router.register('dev/games', DevGameViewSet, basename='dev-games')

urlpatterns = [
    path('dev/stream-settings/', StreamSettingsView.as_view(), name='stream-settings'),
    path('dev/stream-settings/live/', StreamLiveView.as_view(), name='stream-live'),
] + router.urls
