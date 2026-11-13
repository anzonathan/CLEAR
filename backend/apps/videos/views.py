"""Video views for CLEAR."""

import os
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.connections.models import Connection
from apps.users.permissions import IsAdminOrDeveloper
from .models import SharedVideo
from .serializers import SharedVideoSerializer, VideoUploadSerializer


class VideoViewSet(viewsets.ModelViewSet):
    """ViewSet for video operations."""

    serializer_class = SharedVideoSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        return SharedVideo.objects.filter(
            connection__in=Connection.objects.filter(
                Q(user_a=user) | Q(user_b=user)
            )
        ).select_related('uploader', 'connection').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Upload a new video."""
        serializer = VideoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection_id = serializer.validated_data['connection_id']
        video_file = serializer.validated_data['file']
        video_type = serializer.validated_data.get('type', 'recorded')

        # Verify user has access to this connection
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

        # Save the file
        upload_dir = Path(settings.MEDIA_ROOT) / 'videos' / connection_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / video_file.name
        with open(file_path, 'wb+') as f:
            for chunk in video_file.chunks():
                f.write(chunk)

        # Create video record
        video = SharedVideo.objects.create(
            uploader=request.user,
            connection=connection,
            file_path=str(file_path.relative_to(settings.MEDIA_ROOT)),
            file_name=video_file.name,
            file_size=video_file.size,
            mime_type=video_file.content_type,
            type=video_type,
        )

        return Response(
            SharedVideoSerializer(video).data,
            status=status.HTTP_201_CREATED
        )


class DevVideoViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for developer video access."""

    serializer_class = SharedVideoSerializer
    permission_classes = [IsAuthenticated, IsAdminOrDeveloper]
    queryset = SharedVideo.objects.all().select_related('uploader').order_by('-created_at')
