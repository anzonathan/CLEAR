"""Field WebSocket consumers for CLEAR - Camera streaming."""

import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


def get_field_manager():
    """Get the field manager instance."""
    try:
        from src.capture.manager import FieldManager
        return FieldManager(settings.CLEAR_DATA_DIR)
    except ImportError:
        return None


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
        if not manager or manager.get_camera(self.camera_id) is None:
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
                    'camera': camera
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

        if bytes_data:
            manager.submit_jpeg(self.camera_id, bytes_data)
        elif text_data:
            manager.heartbeat(self.camera_id)

    async def status_pusher(self):
        """Push status updates to the client."""
        manager = get_field_manager()
        if not manager:
            return

        while self.connected:
            try:
                camera = manager.get_camera(self.camera_id)
                await self.send(text_data=json.dumps({
                    'type': 'status',
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
