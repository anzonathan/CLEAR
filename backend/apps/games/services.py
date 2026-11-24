"""Bridge between Game rows and the in-process field manager (cameras, match runtime, recorder)."""

import logging
import threading
from pathlib import Path

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.field.views import get_field_manager

from .models import Game

log = logging.getLogger(__name__)

END_LABEL = {'end_a': 'End A', 'end_b': 'End B'}


class GameError(Exception):
    """A user-facing error; the message is shown as-is."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require_manager():
    manager = get_field_manager()
    if manager is None:
        raise GameError('Camera service is unavailable.', status=503)
    return manager


def camera_state(camera_id):
    """Public, token-free view of one camera slot."""
    if not camera_id:
        return None
    manager = get_field_manager()
    cam = manager.get_camera(camera_id) if manager else None
    if cam is None:
        return {'id': camera_id, 'online': False, 'active': False, 'missing': True}
    return {
        'id': camera_id,
        'online': bool(cam.get('online')),
        'active': bool(cam.get('active')),
        'fps': cam.get('fps'),
        'calibrated': bool((cam.get('calibration') or {}).get('ready')),
    }


def camera_token(camera_id):
    manager = get_field_manager()
    cam = manager.registry.get(camera_id) if manager and camera_id else None
    return cam.get('token') if cam else None


def claim_end(game, user, end):
    """Give `user` the camera slot for `end`, creating the field camera. Releases their other slot."""
    if end not in END_LABEL:
        raise GameError('Pick End A or End B.')
    if game.status != 'scheduled':
        raise GameError('Cameras can only be set before the game starts.')
    holder = game.camera_a_user_id if end == 'end_a' else game.camera_b_user_id
    if holder and holder != user.id:
        raise GameError(f'{END_LABEL[end]} is already taken by your partner.', status=409)
    if game.slot_for(user) == end:
        return game

    manager = require_manager()
    release_end(game, user, save=False)
    cam = manager.create_camera(f'{game} · {END_LABEL[end]}', 'browser')
    manager.update_camera(str(cam['id']), end=end, court_mode=game.court_mode)
    if end == 'end_a':
        game.camera_a_id, game.camera_a_user = str(cam['id']), user
    else:
        game.camera_b_id, game.camera_b_user = str(cam['id']), user
    game.save()
    return game


def release_end(game, user, save=True):
    """Drop the slot `user` holds, deleting its field camera."""
    slot = game.slot_for(user)
    if slot is None:
        return game
    if game.status == 'live':
        raise GameError('Stop the game before changing cameras.')
    manager = get_field_manager()
    cam_id = game.camera_a_id if slot == 'end_a' else game.camera_b_id
    if manager and cam_id:
        manager.delete_camera(cam_id)
    if slot == 'end_a':
        game.camera_a_id, game.camera_a_user = '', None
    else:
        game.camera_b_id, game.camera_b_user = '', None
    if save:
        game.save()
    return game


def start_game(game):
    """Start live two-camera analysis and record both feeds.

    Idempotent: both phones auto-start once their cameras are steady, so the second
    call finds the game live and returns it unchanged. The row lock stops two racing
    calls from starting the match twice.
    """
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        if locked.status == 'live':
            return locked
        return _start_locked(locked)


def _start_locked(game):
    if game.status != 'scheduled':
        raise GameError('This game has already been played or cancelled.')
    if not (game.camera_a_id and game.camera_b_id):
        raise GameError('Both players need to set their camera first.')
    if Game.objects.filter(status='live').exclude(id=game.id).exists():
        raise GameError('Another game is live right now. Try again when it ends.', status=409)

    manager = require_manager()
    try:
        manager.start_match(game.camera_a_id, game.camera_b_id)
    except ValueError as exc:
        raise GameError(str(exc))
    game.match_id = manager.match_id or ''
    try:
        rec = manager.start_recording([game.camera_a_id, game.camera_b_id], name=str(game))
        game.recording_id = str(rec.get('id') or '')
    except ValueError as exc:
        # Live analysis still runs; only the recording for later review is lost.
        log.warning('Game %s: recording not started: %s', game.id, exc)
    game.status = 'live'
    game.started_at = timezone.now()
    game.save()
    return game


def stop_game(game):
    if game.status != 'live':
        raise GameError('This game is not live.')
    manager = get_field_manager()
    if manager:
        if manager.recording is not None and manager.recording.id == game.recording_id:
            try:
                manager.stop_recording()
            except ValueError:
                pass
        if game.match_id and manager.match_id == game.match_id:
            manager.stop_match()
    game.status = 'completed'
    game.ended_at = timezone.now()
    game.save()
    return game


def recording_files(game):
    """[(camera_id, raw_video_path)] for a finished game's recording."""
    manager = get_field_manager()
    if not manager or not game.recording_id:
        return []
    meta = manager.get_recording(game.recording_id) or {}
    root = Path(manager.data_dir) / 'recordings' / game.recording_id
    out = []
    for cam in meta.get('cameras') or []:
        for f in cam.get('files') or []:
            if str(f.get('filename', '')).endswith('_raw.mp4'):
                out.append((str(cam.get('camera_id')), root / f['filename']))
    return out


def analysis_dir(game):
    manager = require_manager()
    return Path(manager.data_dir) / 'analysis' / game.id


def start_analysis(game):
    """Run the full offline pipeline on each recorded camera in a background thread."""
    if game.status != 'completed':
        raise GameError('Only finished games can be analysed.')
    if game.analysis_status == 'running':
        raise GameError('Analysis is already running.', status=409)
    files = recording_files(game)
    if not files:
        raise GameError('This game has no recorded video to analyse.')
    out_root = analysis_dir(game)
    game.analysis_status = 'running'
    game.save(update_fields=['analysis_status', 'updated_at'])
    threading.Thread(target=_run_analysis, args=(game.id, files, out_root), daemon=True).start()
    return game


def _run_analysis(game_id, files, out_root):
    close_old_connections()
    try:
        from src.calibration.homography import CourtCalibrator
        from src.pipeline import ClearPipeline

        game = Game.objects.get(id=game_id)
        manager = get_field_manager()
        results = {}
        for camera_id, path in files:
            if not path.exists():
                results[camera_id] = {'error': 'Recording file is missing.'}
                continue
            calib = None
            calib_path = manager.registry.calibration_path(camera_id) if manager else None
            if calib_path and calib_path.exists():
                calib = CourtCalibrator.load(calib_path)
            end = 'end_a' if camera_id == game.camera_a_id else 'end_b'
            pipeline = ClearPipeline(calibrator=calib, court_mode=game.court_mode)
            report = pipeline.run_video(path, out_root / camera_id)
            report.pop('video_out_path', None)
            results[end] = {'camera_id': camera_id, 'calibrated': calib is not None, **report}
        Game.objects.filter(id=game_id).update(
            analysis_status='done', analysis={'cameras': results, 'finished_at': timezone.now().isoformat()}
        )
    except Exception as exc:  # surface any pipeline failure to the dev UI
        log.exception('Analysis failed for game %s', game_id)
        Game.objects.filter(id=game_id).update(analysis_status='failed', analysis={'error': str(exc)})
    finally:
        close_old_connections()
