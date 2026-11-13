"""Live sessions URL configuration."""

from django.urls import path
from .views import LiveSessionViewSet

urlpatterns = [
    path('live/start/', LiveSessionViewSet.as_view({'post': 'start'}), name='live-start'),
    path('live/end/', LiveSessionViewSet.as_view({'post': 'end'}), name='live-end'),
    path('live/active/', LiveSessionViewSet.as_view({'get': 'active'}), name='live-active'),
]
