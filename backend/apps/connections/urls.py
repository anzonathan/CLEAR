"""Connections URL configuration."""

from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import PairCodeViewSet, ConnectionViewSet

router = DefaultRouter()
router.register('connections', ConnectionViewSet, basename='connections')

urlpatterns = [
    path('pair/generate/', PairCodeViewSet.as_view({'post': 'generate'}), name='pair-generate'),
    path('pair/join/', PairCodeViewSet.as_view({'post': 'join'}), name='pair-join'),
] + router.urls
