"""Live session views for CLEAR."""

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.connections.models import Connection
from .models import LiveSession
from .serializers import (
    LiveSessionSerializer,
    StartSessionSerializer,
    EndSessionSerializer
)


class LiveSessionViewSet(viewsets.GenericViewSet):
    """ViewSet for live session operations."""

    serializer_class = LiveSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return LiveSession.objects.filter(
            connection__in=Connection.objects.filter(
                Q(user_a=user) | Q(user_b=user)
            ),
            active=True
        ).select_related('connection', 'connection__user_a', 'connection__user_b')

    @action(detail=False, methods=['post'], url_path='start')
    def start(self, request):
        """Start a new live session."""
        serializer = StartSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection_id = serializer.validated_data['connectionId']

        # Verify connection exists and user has access
        try:
            connection = Connection.objects.get(
                Q(user_a=request.user) | Q(user_b=request.user),
                id=connection_id,
                active=True
            )
        except Connection.DoesNotExist:
            return Response(
                {'error': 'Connection not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create new session
        session = LiveSession.objects.create(
            connection=connection,
            started_by=request.user
        )

        return Response({'sessionId': session.id})

    @action(detail=False, methods=['post'], url_path='end')
    def end(self, request):
        """End a live session."""
        serializer = EndSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data['sessionId']

        try:
            session = LiveSession.objects.get(id=session_id)
            session.active = False
            session.ended_at = timezone.now()
            session.save()
        except LiveSession.DoesNotExist:
            pass  # Silently ignore if session doesn't exist

        return Response({'success': True})

    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        """Get active live sessions."""
        sessions = self.get_queryset()
        serializer = LiveSessionSerializer(
            sessions, many=True, context={'request': request}
        )
        return Response(serializer.data)
