"""Field URL configuration."""

from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CameraViewSet,
    RecordingViewSet,
    FieldDeactivateView,
    FieldActiveView,
    FieldMatchView,
    FieldMatchStopView,
    FieldMatchFusedView,
    FieldHealthView,
)

router = DefaultRouter()
router.register('cameras', CameraViewSet, basename='cameras')
router.register('recordings', RecordingViewSet, basename='recordings')

urlpatterns = router.urls + [
    path('deactivate/', FieldDeactivateView.as_view(), name='field-deactivate'),
    path('active/', FieldActiveView.as_view(), name='field-active'),
    path('match/', FieldMatchView.as_view(), name='field-match'),
    path('match/stop/', FieldMatchStopView.as_view(), name='field-match-stop'),
    path('match/fused/', FieldMatchFusedView.as_view(), name='field-match-fused'),
    path('record/start/', RecordingViewSet.as_view({'post': 'start'}), name='record-start'),
    path('record/stop/', RecordingViewSet.as_view({'post': 'stop'}), name='record-stop'),
    path('record/', RecordingViewSet.as_view({'get': 'status'}), name='record-status'),
    path('health/', FieldHealthView.as_view(), name='field-health'),
]
