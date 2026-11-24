from rest_framework.routers import DefaultRouter

from .views import DevGameViewSet, GameViewSet

router = DefaultRouter()
router.register('games', GameViewSet, basename='games')
router.register('dev/games', DevGameViewSet, basename='dev-games')

urlpatterns = router.urls
