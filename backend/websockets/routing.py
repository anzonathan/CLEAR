"""WebSocket URL routing for CLEAR."""

from django.urls import re_path
from . import signaling, field

websocket_urlpatterns = [
    re_path(r'ws/signaling/$', signaling.SignalingConsumer.as_asgi()),
    re_path(r'ws/field/view/(?P<camera_id>\w+)/$', field.ViewStreamConsumer.as_asgi()),
    re_path(r'ws/field/ingest/(?P<camera_id>\w+)/$', field.IngestStreamConsumer.as_asgi()),
    re_path(r'ws/field/match/$', field.MatchStreamConsumer.as_asgi()),
]
