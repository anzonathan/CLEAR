"""Field WebSocket consumers for CLEAR - Camera streaming."""

import asyncio
import json
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

# Per-camera ingest stats, measured here (bytes) plus what the phone reports it is using.
# Read by the dev Streaming page and the live view. In-process: one Daphne worker.
_INGEST_STATS = {}
# Byte/frame counters per camera, not per connection: a consumer dropped without a clean
# disconnect (e.g. a Redis channel-layer timeout) must not report zeros for a live phone.
_INGEST_ACC = {}
_SETTINGS_CACHE = {'at': 0.0, 'value': None}


def _count_frame(camera_id, nbytes):
    acc = _INGEST_ACC.setdefault(camera_id, {'bytes': 0, 'frames': 0, 'since': time.time()})
    acc['bytes'] += nbytes
    acc['frames'] += 1


def _roll_rates(camera_id):
    """Turn the counters into rates once per window. Safe to call from any connection."""
    now = time.time()
    acc = _INGEST_ACC.setdefault(camera_id, {'bytes': 0, 'frames': 0, 'since': now})
    span = now - acc['since']
    if span < 3.0:  # long enough that one late frame does not swing the rate
        return
    st = _INGEST_STATS.setdefault(camera_id, {})
    st.update({
        'kbps': round(acc['bytes'] * 8 / 1000 / span, 1),
        'fps': round(acc['frames'] / span, 1),
        'avg_kb': round(acc['bytes'] / 1000 / acc['frames'], 1) if acc['frames'] else None,
        'updated': now,
    })
    acc.update(bytes=0, frames=0, since=now)


def ingest_snapshot():
    """Stats for phones that reported in the last 10 s."""
    now = time.time()
    # 'seen' is set only by traffic from the phone itself, so zombie pushers cannot keep a gone phone listed.
    return {cid: dict(st) for cid, st in _INGEST_STATS.items() if now - st.get('seen', 0) < 10}


@database_sync_to_async
def _load_stream_settings():
    from apps.games.models import StreamSettings
    return StreamSettings.load().to_client()


async def stream_settings():
    """Phone encoding settings, cached for 2 s so every pusher tick does not hit the DB."""
    if _SETTINGS_CACHE['value'] is None or time.time() - _SETTINGS_CACHE['at'] > 2:
        _SETTINGS_CACHE['value'] = await _load_stream_settings()
        _SETTINGS_CACHE['at'] = time.time()
    return _SETTINGS_CACHE['value']


def get_field_manager():
    """The process-wide field manager shared with the REST views.

    A fresh FieldManager here would have no running match, so ingested frames
    would be dropped and viewers would never see the live runtime.
    """
    from apps.field.views import get_field_manager as shared
    return shared()


def is_dev(scope):
    user = scope.get('user')
    return bool(user and user.is_authenticated and getattr(user, 'role', '') in ('admin', 'developer'))


class ViewStreamConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for viewing camera streams."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera_id = None
        self.streaming = False

    async def connect(self):
        """Handle WebSocket connection."""
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']

        manager = get_field_manager()
        if not is_dev(self.scope) or not manager or manager.get_camera(self.camera_id) is None:
            await self.accept()
            await self.close(code=1008)
            return

        await self.accept()
        manager.viewer_count(self.camera_id, 1)
        self.streaming = True

        # Start streaming loop
        asyncio.create_task(self.stream_loop())

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        self.streaming = False
        manager = get_field_manager()
        if manager and self.camera_id:
            manager.viewer_count(self.camera_id, -1)

    async def stream_loop(self):
        """Stream frames to the client."""
        manager = get_field_manager()
        if not manager:
            return

        last_index = -1

        while self.streaming:
            try:
                camera = manager.get_camera(self.camera_id)

                if camera is None:
                    await self.send(text_data=json.dumps({
                        'type': 'state',
                        'active': False,
                        'missing': True
                    }))
                    await asyncio.sleep(0.5)
                    continue

                if not camera.get('active'):
                    await self.send(text_data=json.dumps({
                        'type': 'state',
                        'active': False,
                        'camera': camera
                    }))
                    await asyncio.sleep(0.5)
                    continue

                frame_index = int(camera.get('frame_index') or 0)
                if frame_index != last_index:
                    jpeg = manager.snapshot_jpeg(self.camera_id)
                    if jpeg:
                        await self.send(bytes_data=jpeg)
                        last_index = frame_index

                await self.send(text_data=json.dumps({
                    'type': 'meta',
                    'camera': camera,
                    'stream': _INGEST_STATS.get(self.camera_id),
                }))
                await asyncio.sleep(0.05)

            except Exception:
                break


class IngestStreamConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for ingesting camera frames."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera_id = None
        self.connected = False

    async def connect(self):
        """Handle WebSocket connection."""
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        token = self.scope.get('query_string', b'').decode()

        # Parse token from query string
        token_value = ''
        for param in token.split('&'):
            if param.startswith('token='):
                token_value = param[6:]
                break

        manager = get_field_manager()
        if not manager or not manager.registry.token_matches(self.camera_id, token_value):
            await self.accept()
            await self.close(code=1008)
            return

        await self.accept()
        manager.set_ingest_connected(self.camera_id, True)
        self.connected = True

        # Start status pusher
        asyncio.create_task(self.status_pusher())

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        self.connected = False
        manager = get_field_manager()
        if manager and self.camera_id:
            manager.set_ingest_connected(self.camera_id, False)

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming data."""
        manager = get_field_manager()
        if not manager:
            return

        _INGEST_STATS.setdefault(self.camera_id, {})['seen'] = time.time()
        if bytes_data:
            _count_frame(self.camera_id, len(bytes_data))
            manager.submit_jpeg(self.camera_id, bytes_data)
        elif text_data:
            manager.heartbeat(self.camera_id)
            if text_data.startswith('{'):
                # The phone reports the encoding it is actually using (adaptive may have stepped down).
                try:
                    msg = json.loads(text_data)
                except json.JSONDecodeError:
                    return
                if msg.get('type') == 'stats':
                    st = _INGEST_STATS.setdefault(self.camera_id, {})
                    st.update({
                        'width': msg.get('w'), 'height': msg.get('h'), 'quality': msg.get('q'),
                        'target_fps': msg.get('fps'), 'throttled': bool(msg.get('throttled')),
                        'updated': time.time(),
                    })

    async def status_pusher(self):
        """Push status updates to the client."""
        manager = get_field_manager()
        if not manager:
            return

        while self.connected:
            try:
                _roll_rates(self.camera_id)

                camera = manager.get_camera(self.camera_id)
                await self.send(text_data=json.dumps({
                    'type': 'status',
                    'stream': await stream_settings(),
                    # 'preview' = developer is calibrating; the phone must not announce a game start.
                    'mode': 'preview' if manager.in_preview(self.camera_id) else 'live',
                    'active': bool(camera and camera.get('active')),
                    'online': bool(camera and camera.get('online')),
                }))
                await asyncio.sleep(2.0)
            except Exception:
                break


class MatchStreamConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for match streaming."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.streaming = False

    async def connect(self):
        """Handle WebSocket connection."""
        await self.accept()
        if not is_dev(self.scope):
            await self.close(code=1008)
            return
        self.streaming = True
        asyncio.create_task(self.stream_loop())

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        self.streaming = False

    async def stream_loop(self):
        """Stream match data to the client."""
        manager = get_field_manager()
        if not manager:
            return

        last_index = -1

        while self.streaming:
            try:
                match = manager.match_stats()

                if match is None:
                    await self.send(text_data=json.dumps({
                        'type': 'state',
                        'active': False
                    }))
                    await asyncio.sleep(0.5)
                    continue

                fused = match.get('fused') or {}
                idx = int(fused.get('frame_index') or 0)

                if idx != last_index:
                    last_index = idx
                    await self.send(text_data=json.dumps({
                        'type': 'fused',
                        'match_id': manager.match_id,
                        'fused': fused
                    }))

                await asyncio.sleep(0.05)

            except Exception:
                break
