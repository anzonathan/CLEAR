from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import DatasetExportViewSet, DevGameViewSet, GameViewSet, StreamLiveView, StreamSettingsView

router = DefaultRouter()
router.register('games', GameViewSet, basename='games')
router.register('dev/games', DevGameViewSet, basename='dev-games')
router.register('dev/datasets', DatasetExportViewSet, basename='dev-datasets')

urlpatterns = [
    path('dev/stream-settings/', StreamSettingsView.as_view(), name='stream-settings'),
    path('dev/stream-settings/live/', StreamLiveView.as_view(), name='stream-live'),
] + router.urls
