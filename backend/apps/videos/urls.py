"""Videos URL configuration."""

from rest_framework.routers import DefaultRouter
from .views import VideoViewSet, DevVideoViewSet

router = DefaultRouter()
router.register('videos', VideoViewSet, basename='videos')
router.register('dev/videos', DevVideoViewSet, basename='dev-videos')

urlpatterns = router.urls
