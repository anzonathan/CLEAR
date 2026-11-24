"""Game views: players schedule and film games; developers watch and analyse them."""

from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.connections.models import Connection
from apps.users.permissions import IsAdminOrDeveloper

from . import services
from .models import Game
from .serializers import DevGameSerializer, GameCreateSerializer, GameSerializer, GameUpdateSerializer


def _error(exc):
    return Response({'error': str(exc)}, status=exc.status)


class GameViewSet(viewsets.ModelViewSet):
    """Games for the requesting user's active connections."""

    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        user = self.request.user
        qs = Game.objects.filter(
            Q(connection__user_a=user) | Q(connection__user_b=user), connection__active=True
        ).select_related('connection__user_a', 'connection__user_b', 'camera_a_user', 'camera_b_user')
        connection = self.request.query_params.get('connection')
        if connection:
            qs = qs.filter(connection_id=connection)
        if self.request.query_params.get('upcoming'):
            qs = qs.filter(status__in=['scheduled', 'live']).order_by('scheduled_at')
        return qs

    def create(self, request):
        data = GameCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        try:
            connection = Connection.objects.get(
                Q(user_a=request.user) | Q(user_b=request.user), id=v['connection_id'], active=True
            )
        except Connection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        game = Game.objects.create(
            connection=connection, created_by=request.user, scheduled_at=v['scheduled_at'],
            court_mode=v['court_mode'], title=v.get('title', ''),
        )
        return Response(self.get_serializer(game).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        game = self.get_object()
        if game.status != 'scheduled':
            return Response({'error': 'Only scheduled games can be changed.'}, status=400)
        data = GameUpdateSerializer(game, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(self.get_serializer(game).data)

    def destroy(self, request, *args, **kwargs):
        """Cancel a game that has not started. Frees both cameras."""
        game = self.get_object()
        if game.status != 'scheduled':
            return Response({'error': 'Only scheduled games can be cancelled.'}, status=400)
        for user in (game.camera_a_user, game.camera_b_user):
            if user is not None:
                services.release_end(game, user, save=False)
        game.status = 'cancelled'
        game.save()
        return Response(self.get_serializer(game).data)

    @action(detail=True, methods=['post', 'delete'])
    def camera(self, request, pk=None):
        """POST {end: end_a|end_b} claims that end for my phone. DELETE releases it."""
        game = self.get_object()
        try:
            if request.method == 'DELETE':
                services.release_end(game, request.user)
            else:
                services.claim_end(game, request.user, request.data.get('end'))
        except services.GameError as exc:
            return _error(exc)
        return Response(self.get_serializer(game).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        game = self.get_object()
        try:
            game = services.start_game(game)
        except services.GameError as exc:
            return _error(exc)
        return Response(self.get_serializer(game).data)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        game = self.get_object()
        try:
            services.stop_game(game)
        except services.GameError as exc:
            return _error(exc)
        return Response(self.get_serializer(game).data)


class DevGameViewSet(viewsets.ReadOnlyModelViewSet):
    """Every game, for developers analysing pairs live or from recordings."""

    serializer_class = DevGameSerializer
    permission_classes = [IsAuthenticated, IsAdminOrDeveloper]

    def get_queryset(self):
        qs = Game.objects.exclude(status='cancelled').select_related(
            'connection__user_a', 'connection__user_b', 'camera_a_user', 'camera_b_user'
        )
        st = self.request.query_params.get('status')
        return qs.filter(status=st) if st else qs

    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        game = self.get_object()
        try:
            services.start_analysis(game)
        except services.GameError as exc:
            return _error(exc)
        return Response(self.get_serializer(game).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Let a developer end a live game, e.g. when players leave it running."""
        game = self.get_object()
        try:
            services.stop_game(game)
        except services.GameError as exc:
            return _error(exc)
        return Response(self.get_serializer(game).data)

    @action(detail=True, methods=['get'], url_path=r'chart/(?P<end>end_a|end_b)')
    def chart(self, request, pk=None, end=None):
        """Court analytics PNG for one end, produced by the offline analysis."""
        game = self.get_object()
        cam_id = game.camera_a_id if end == 'end_a' else game.camera_b_id
        path = services.analysis_dir(game) / cam_id / 'court_analytics.png'
        if not cam_id or not path.exists():
            raise Http404
        return FileResponse(open(path, 'rb'), content_type='image/png')
