"""Connection views for CLEAR."""

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PairCode, Connection
from .serializers import (
    PairCodeSerializer,
    ConnectionSerializer,
    ConnectionDetailSerializer,
    JoinCodeSerializer
)


class PairCodeViewSet(viewsets.GenericViewSet):
    """ViewSet for pair code operations."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """Generate a new pair code."""
        pair_code = PairCode.objects.create(creator=request.user)
        serializer = PairCodeSerializer(pair_code)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='join')
    def join(self, request):
        """Join via a pair code."""
        serializer = JoinCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data['code'].upper()

        # Find valid pair code
        try:
            pair_code = PairCode.objects.get(
                code=code,
                used=False,
                expires_at__gt=timezone.now()
            )
        except PairCode.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired code'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Can't pair with yourself
        if pair_code.creator_id == request.user.id:
            return Response(
                {'error': 'Cannot pair with yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if connection already exists
        existing = Connection.objects.filter(
            Q(user_a=pair_code.creator, user_b=request.user) |
            Q(user_a=request.user, user_b=pair_code.creator)
        ).first()

        if existing:
            return Response(
                {'error': 'Already connected', 'connectionId': existing.id},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark code as used
        pair_code.used = True
        pair_code.used_by = request.user
        pair_code.used_at = timezone.now()
        pair_code.save()

        # Create connection
        connection = Connection.objects.create(
            user_a=pair_code.creator,
            user_b=request.user,
            pair_code=pair_code
        )

        return Response({
            'connectionId': connection.id,
            'connectedWith': {
                'id': pair_code.creator.id,
                'name': pair_code.creator.name,
                'email': pair_code.creator.email,
                'image': pair_code.creator.image,
            }
        })


class ConnectionViewSet(viewsets.ModelViewSet):
    """ViewSet for connection operations."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConnectionDetailSerializer
        return ConnectionSerializer

    def get_queryset(self):
        return Connection.objects.filter(
            Q(user_a=self.request.user) | Q(user_b=self.request.user),
            active=True
        ).select_related('user_a', 'user_b').order_by('-created_at')

    def destroy(self, request, *args, **kwargs):
        """End a connection (soft delete)."""
        connection = self.get_object()
        connection.active = False
        connection.save()
        return Response({'success': True})
