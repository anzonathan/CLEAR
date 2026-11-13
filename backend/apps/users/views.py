"""User views for CLEAR."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import UserSerializer, AdminUserSerializer, UpdateRoleSerializer
from .permissions import IsAdminUser


class UserViewSet(viewsets.GenericViewSet):
    """ViewSet for user operations."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(id=self.request.user.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user details."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Update current user's profile."""
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AdminUserViewSet(viewsets.ModelViewSet):
    """ViewSet for admin user management."""

    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = User.objects.all().order_by('-created_at')

    @action(detail=True, methods=['patch'], url_path='role')
    def update_role(self, request, pk=None):
        """Update a user's role."""
        user = self.get_object()

        if user.id == request.user.id:
            return Response(
                {'error': 'Cannot change your own role'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UpdateRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user.role = serializer.validated_data['role']
        user.save()

        return Response({'success': True})

    def destroy(self, request, *args, **kwargs):
        """Delete a user."""
        user = self.get_object()

        if user.id == request.user.id:
            return Response(
                {'error': 'Cannot delete yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.delete()
        return Response({'success': True})


class AdminStatsView(APIView):
    """View for admin statistics."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        """Get system statistics."""
        from apps.connections.models import Connection
        from apps.videos.models import SharedVideo
        from apps.live.models import LiveSession

        return Response({
            'totalUsers': User.objects.count(),
            'activeConnections': Connection.objects.filter(active=True).count(),
            'totalVideos': SharedVideo.objects.count(),
            'activeSessions': LiveSession.objects.filter(active=True).count(),
        })
