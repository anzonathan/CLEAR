"""Field views for CLEAR - Camera management and CV endpoints."""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Camera, Recording
from .serializers import (
    CameraSerializer,
    CameraCreateSerializer,
    CameraUpdateSerializer,
    RecordingSerializer,
    CalibrationRequestSerializer,
    MatchRequestSerializer,
    RecordStartSerializer,
)

# Field manager will be initialized when ML modules are available
_field_manager = None


def get_field_manager():
    """Get or initialize the field manager."""
    global _field_manager
    if _field_manager is None:
        try:
            from src.capture.manager import FieldManager
            _field_manager = FieldManager(settings.CLEAR_DATA_DIR)
        except ImportError:
            pass
    return _field_manager


class CameraViewSet(viewsets.ModelViewSet):
    """ViewSet for camera operations."""

    queryset = Camera.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return CameraCreateSerializer
        if self.action in ('update', 'partial_update'):
            return CameraUpdateSerializer
        return CameraSerializer

    def list(self, request):
        """List all cameras."""
        manager = get_field_manager()
        if manager:
            return Response({
                'cameras': manager.list_cameras(),
                'active_id': manager.active_id,
                'match_id': manager.match_id
            })
        cameras = self.get_queryset()
        serializer = self.get_serializer(cameras, many=True)
        return Response({
            'cameras': serializer.data,
            'active_id': None,
            'match_id': None
        })

    def create(self, request):
        """Create a new camera."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        manager = get_field_manager()
        if manager:
            camera = manager.create_camera(
                serializer.validated_data['name'],
                serializer.validated_data.get('source', 'browser'),
                serializer.validated_data.get('rtsp_url', '')
            )
            end = serializer.validated_data.get('end')
            if end and end != 'none':
                manager.update_camera(str(camera['id']), end=end)
            return Response(manager.get_camera(str(camera['id'])) or camera)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        """Activate a camera."""
        manager = get_field_manager()
        if manager:
            camera = manager.activate(pk)
            if camera is None:
                return Response({'error': 'Camera not found'}, status=status.HTTP_404_NOT_FOUND)
            return Response(camera)
        return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=True, methods=['get'], url_path='snapshot\\.jpg')
    def snapshot(self, request, pk=None):
        """Get a snapshot from the camera."""
        raw = request.query_params.get('raw', 'false').lower() == 'true'
        manager = get_field_manager()
        if manager:
            jpeg = manager.snapshot_jpeg(pk, raw=raw)
            if jpeg is None:
                return Response({'error': 'No frame available'}, status=status.HTTP_404_NOT_FOUND)
            return HttpResponse(jpeg, content_type='image/jpeg')
        return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=True, methods=['get', 'post'], url_path='calibration')
    def calibration(self, request, pk=None):
        """Get or save calibration for a camera."""
        manager = get_field_manager()
        if not manager:
            return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if manager.get_camera(pk) is None:
            return Response({'error': 'Camera not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.method == 'GET':
            return Response({'calibration': manager.get_calibration(pk)})

        serializer = CalibrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cal = manager.save_calibration(
                pk,
                serializer.validated_data['anchors_px'],
                method=serializer.validated_data['method']
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if cal is None:
            return Response({'error': 'Camera not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'ok': True,
            'method': cal.method,
            'anchors_px': {k: list(v) for k, v in cal.anchors_px.items()},
            'reproj_error_cm': round(cal.reproj_error_cm, 2),
        })

    @action(detail=True, methods=['post'], url_path='calibration/auto')
    def auto_calibrate(self, request, pk=None):
        """Auto-calibrate a camera."""
        manager = get_field_manager()
        if not manager:
            return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            return Response(manager.auto_calibrate(pk))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='events')
    def events(self, request, pk=None):
        """Get events for a camera."""
        limit = int(request.query_params.get('limit', 40))
        manager = get_field_manager()
        if not manager:
            return Response({'events': []})

        if manager.get_camera(pk) is None:
            return Response({'error': 'Camera not found'}, status=status.HTTP_404_NOT_FOUND)

        path = manager.data_dir / 'sessions' / pk / 'events.jsonl'
        if not path.exists():
            return Response({'events': []})

        import json
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return Response({'events': events})


class FieldDeactivateView(APIView):
    """Deactivate the active camera."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        manager = get_field_manager()
        if manager:
            manager.deactivate()
        return Response({'ok': True, 'active_id': None})


class FieldActiveView(APIView):
    """Get the active camera."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = get_field_manager()
        if manager:
            return Response({
                'camera': manager.active_stats(),
                'active_id': manager.active_id
            })
        return Response({'camera': None, 'active_id': None})


class FieldMatchView(APIView):
    """Match operations for two cameras."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current match status."""
        manager = get_field_manager()
        if manager:
            return Response({
                'match': manager.match_stats(),
                'match_id': manager.match_id
            })
        return Response({'match': None, 'match_id': None})

    def post(self, request):
        """Start a match."""
        serializer = MatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        manager = get_field_manager()
        if not manager:
            return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            match = manager.start_match(
                serializer.validated_data['camera_a_id'],
                serializer.validated_data['camera_b_id']
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'match': match, 'match_id': manager.match_id})


class FieldMatchStopView(APIView):
    """Stop the current match."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        manager = get_field_manager()
        if manager:
            manager.stop_match()
        return Response({'ok': True, 'match_id': None})


class FieldMatchFusedView(APIView):
    """Get fused match data."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = get_field_manager()
        if manager:
            return Response({
                'match_id': manager.match_id,
                'fused': manager.fused_snapshot()
            })
        return Response({'match_id': None, 'fused': None})


class RecordingViewSet(viewsets.ModelViewSet):
    """ViewSet for recording operations."""

    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='start')
    def start(self, request):
        """Start a recording."""
        serializer = RecordStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        manager = get_field_manager()
        if not manager:
            return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            return Response(manager.start_recording(
                serializer.validated_data['camera_ids'],
                serializer.validated_data.get('name', '')
            ))
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='stop')
    def stop(self, request):
        """Stop the current recording."""
        manager = get_field_manager()
        if not manager:
            return Response({'error': 'Field manager not available'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            return Response(manager.stop_recording())
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='status')
    def status(self, request):
        """Get recording status."""
        manager = get_field_manager()
        if manager:
            return Response(manager.recording_status())
        return Response({'recording': False})


class FieldHealthView(APIView):
    """Field health check."""

    permission_classes = [AllowAny]

    def get(self, request):
        manager = get_field_manager()
        return Response({
            'ok': True,
            'active_id': manager.active_id if manager else None,
            'match_id': manager.match_id if manager else None,
            'camera_count': len(manager.registry.list()) if manager else 0,
            'auth_enabled': bool(settings.CLEAR_FIELD_PASSWORD),
        })
