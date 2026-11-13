"""Admin URL configuration."""

from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AdminUserViewSet, AdminStatsView

router = DefaultRouter()
router.register('users', AdminUserViewSet, basename='admin-users')

urlpatterns = router.urls + [
    path('stats/', AdminStatsView.as_view(), name='admin-stats'),
]
