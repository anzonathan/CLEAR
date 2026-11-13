"""WebRTC signaling consumer for CLEAR."""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async


class SignalingConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for WebRTC signaling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.user_id = None
        self.room_group_name = None

    async def connect(self):
        """Handle WebSocket connection."""
        await self.accept()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.room_group_name and self.user_id:
            # Notify other peers
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'peer_left',
                    'user_id': self.user_id,
                }
            )
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'join':
                await self.handle_join(data)
            elif message_type in ('offer', 'answer', 'ice-candidate'):
                await self.handle_signal(data)
            elif message_type == 'leave':
                await self.handle_leave()
            else:
                await self.send_error('Unknown message type')
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON')
        except Exception as e:
            await self.send_error(str(e))

    async def handle_join(self, data):
        """Handle join request."""
        session_id = data.get('sessionId')
        user_id = data.get('userId')

        if not session_id or not user_id:
            await self.send_error('Missing sessionId or userId')
            return

        # Verify session
        if not await self.verify_session(session_id, user_id):
            await self.send_error('Invalid session or unauthorized')
            return

        self.session_id = session_id
        self.user_id = user_id
        self.room_group_name = f'signaling_{session_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Notify other peers
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'peer_joined',
                'user_id': user_id,
                'sender_channel': self.channel_name,
            }
        )

        # Send join confirmation
        await self.send(text_data=json.dumps({
            'type': 'join',
            'sessionId': session_id,
            'peers': [],  # Would need to track peers in Redis for full list
        }))

    async def handle_signal(self, data):
        """Handle signaling message (offer, answer, ice-candidate)."""
        if not self.room_group_name or not self.user_id:
            await self.send_error('Not in a session')
            return

        target_user_id = data.get('userId')
        if not target_user_id:
            await self.send_error('Target user not specified')
            return

        # Forward signal to the room (target will filter)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'forward_signal',
                'signal_type': data.get('type'),
                'from_user_id': self.user_id,
                'to_user_id': target_user_id,
                'payload': data.get('payload'),
            }
        )

    async def handle_leave(self):
        """Handle leave request."""
        if self.room_group_name and self.user_id:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'peer_left',
                    'user_id': self.user_id,
                }
            )
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        self.session_id = None
        self.user_id = None
        self.room_group_name = None

    async def peer_joined(self, event):
        """Handle peer joined event."""
        if event.get('sender_channel') != self.channel_name:
            await self.send(text_data=json.dumps({
                'type': 'peer-joined',
                'userId': event['user_id'],
            }))

    async def peer_left(self, event):
        """Handle peer left event."""
        if event['user_id'] != self.user_id:
            await self.send(text_data=json.dumps({
                'type': 'peer-left',
                'userId': event['user_id'],
            }))

    async def forward_signal(self, event):
        """Handle signal forwarding."""
        # Only send to the target user
        if event['to_user_id'] == self.user_id:
            await self.send(text_data=json.dumps({
                'type': event['signal_type'],
                'userId': event['from_user_id'],
                'payload': event['payload'],
            }))

    async def send_error(self, error):
        """Send error message."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'payload': {'error': error}
        }))

    @database_sync_to_async
    def verify_session(self, session_id, user_id):
        """Verify that the session exists and user has access."""
        from apps.live.models import LiveSession
        from django.db.models import Q

        return LiveSession.objects.filter(
            id=session_id,
            active=True,
            connection__in=LiveSession.objects.filter(
                Q(connection__user_a_id=user_id) | Q(connection__user_b_id=user_id)
            ).values('connection')
        ).exists()
