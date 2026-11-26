"""Bridge between Game rows and the in-process field manager (cameras, match runtime, recorder)."""

import logging
import os
import re
import threading
from pathlib import Path

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.field.views import get_field_manager

from .models import Game

log = logging.getLogger(__name__)

END_LABEL = {'end_a': 'End A', 'end_b': 'End B'}
# Statuses before a game is played: an open invite, or an accepted one.
OPEN_STATUSES = ('pending', 'scheduled')


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
    cal = cam.get('calibration') or {}
    return {
        'id': camera_id,
        'online': bool(cam.get('online')),
        'active': bool(cam.get('active')),
        'preview': manager.in_preview(camera_id),
        'fps': cam.get('fps'),
        'calibrated': bool(cal.get('ready')),
        'calib_method': cal.get('method'),
        'reproj_error_cm': cal.get('reproj_error_cm'),
    }


def camera_token(camera_id):
    manager = get_field_manager()
    cam = manager.registry.get(camera_id) if manager and camera_id else None
    return cam.get('token') if cam else None


def claim_end(game, user, end):
    """Give `user` the camera slot for `end`, creating the field camera. Releases their other slot."""
    if end not in END_LABEL:
        raise GameError('Pick End A or End B.')
    if game.status not in OPEN_STATUSES:
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
    if game.status != 'scheduled':
        # A finished game can share its cameras with the next game (dev "Next game"),
        # so releasing would delete a camera that is still in use.
        raise GameError('Cameras can only be changed before the game starts.')
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


def apply_detector_settings():
    """Runtimes read CLEAR_YOLO_IMGSZ when they start; set it from the dev settings first."""
    from .models import StreamSettings

    os.environ['CLEAR_YOLO_IMGSZ'] = str(StreamSettings.load().yolo_imgsz)


def accept_invite(game, user):
    """The invited player agrees to the game, so it can start."""
    if game.status != 'pending':
        raise GameError('This invite is no longer open.', status=409)
    if not game.awaits(user):
        raise GameError('Your partner has to accept this invite.', status=403)
    game.status = 'scheduled'
    game.save()
    return game


def decline_invite(game, user):
    """The invited player turns the game down. Frees any camera the proposer set."""
    if game.status != 'pending':
        raise GameError('This invite is no longer open.', status=409)
    if not game.awaits(user):
        raise GameError('You sent this invite. Cancel it instead.', status=403)
    _release_all(game)
    game.status = 'declined'
    game.save()
    return game


def _release_all(game):
    for user in (game.camera_a_user, game.camera_b_user):
        if user is not None:
            release_end(game, user, save=False)


def cancel_game(game):
    """Cancel an invite or an accepted game that has not started. Frees both cameras."""
    if game.status not in OPEN_STATUSES:
        raise GameError('Only games that have not started can be cancelled.')
    _release_all(game)
    game.status = 'cancelled'
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
    if game.status == 'pending':
        raise GameError('Waiting for your partner to accept the invite.', status=409)
    if game.status != 'scheduled':
        raise GameError('This game has already been played or cancelled.')
    if not (game.camera_a_id and game.camera_b_id):
        raise GameError('Both players need to set their camera first.')
    if Game.objects.filter(status='live').exclude(id=game.id).exists():
        raise GameError('Another game is live right now. Try again when it ends.', status=409)

    manager = require_manager()
    if manager.in_preview(game.camera_a_id) or manager.in_preview(game.camera_b_id):
        raise GameError('A developer is calibrating the cameras. The game starts once they finish.', status=409)
    if manager.match_preview:
        manager.stop_match()  # a stale preview for another game must not block this one
    apply_detector_settings()
    try:
        manager.start_match(game.camera_a_id, game.camera_b_id)
    except ValueError as exc:
        raise GameError(str(exc))
    game.match_id = manager.match_id or ''
    if not game.dev_mode:  # dev-mode games wait for a developer to start the recording
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


def start_blockers(game):
    """Why a developer can't start this game yet ([] = both players' phones are online)."""
    if game.status != 'scheduled':
        return ['Only scheduled games can be started.']
    out = []
    for end, cam_id, user in (
        ('end_a', game.camera_a_id, game.camera_a_user),
        ('end_b', game.camera_b_id, game.camera_b_user),
    ):
        if not cam_id:
            out.append(f'No player has taken {END_LABEL[end]} yet.')
            continue
        state = camera_state(cam_id) or {}
        who = user.name if user and user.name else 'The player'
        if not state.get('online'):
            out.append(f"{who}'s phone ({END_LABEL[end]}) is offline.")
        elif state.get('preview'):
            out.append(f'{END_LABEL[end]} is in a calibration preview. Stop it first.')
    return out


def dev_start_game(game):
    """Start a scheduled game from dev tools, only when both players' phones are online."""
    blockers = start_blockers(game)
    if blockers:
        raise GameError(' '.join(blockers), status=409)
    return start_game(game)


def recording_state(game):
    """'off' | 'recording' | 'paused' while live; 'saved' / 'none' once the game is over."""
    if game.status != 'live':
        return 'saved' if game.recording_id else 'none'
    manager = get_field_manager()
    rec = getattr(manager, 'recording', None) if manager else None
    if not game.recording_id or rec is None or rec.id != game.recording_id:
        return 'off'
    return 'paused' if getattr(rec, 'paused', False) else 'recording'


def dev_record(game, action):
    """Developer recording control for a live game: start | pause | resume (one file per game)."""
    if game.status != 'live':
        raise GameError('Recording can only be controlled while the game is live.')
    manager = require_manager()
    state = recording_state(game)
    try:
        if action == 'start':
            if state != 'off':
                raise GameError('This game is already recording.' if state == 'recording' else 'Recording is paused: resume it.')
            if game.recording_id:
                raise GameError('This game already has a recording that was closed. Start a next game to record again.')
            if manager.recording is not None:
                raise GameError('Another recording is running on the server.', status=409)
            rec = manager.start_recording([game.camera_a_id, game.camera_b_id], name=str(game))
            game.recording_id = str(rec.get('id') or '')
            game.save(update_fields=['recording_id', 'updated_at'])
        elif action == 'pause':
            if state != 'recording':
                raise GameError('Nothing is recording right now.')
            manager.pause_recording()
        elif action == 'resume':
            if state != 'paused':
                raise GameError('The recording is not paused.')
            manager.resume_recording()
        else:
            raise GameError('action must be start, pause or resume.')
    except ValueError as exc:  # field manager refused (e.g. camera not active)
        raise GameError(str(exc), status=409)
    return game


def _next_title(title):
    base, n = title or '', 2
    m = re.match(r'^(.*?)\s*#(\d+)$', base)
    if m:
        base, n = m.group(1), int(m.group(2)) + 1
    return f'{base or "Game"} #{n}'[:120]


def dev_next_game(game):
    """End this live game (its recording is closed and kept) and start a new game for the same
    players on the same cameras, so phones keep streaming. Dev-mode games start unrecorded."""
    if game.status != 'live':
        raise GameError('Only a live game can roll into a next game.')
    if not (game.camera_a_id and game.camera_b_id):
        raise GameError('Both ends need a camera.')
    nxt = Game.objects.create(
        connection=game.connection, created_by=game.created_by, scheduled_at=timezone.now(),
        court_mode=game.court_mode, title=_next_title(game.title), dev_mode=game.dev_mode,
        # Both players already accepted the game this one continues, so skip the invite.
        status='scheduled', proposed_by=game.proposed_by,
        camera_a_id=game.camera_a_id, camera_a_user=game.camera_a_user,
        camera_b_id=game.camera_b_id, camera_b_user=game.camera_b_user,
    )
    # Link before ending: phones stop polling once they see "completed", so that same
    # response must already say where to go next.
    game.next_game = nxt
    stop_game(game)  # saves status + next_game together, closes the recording
    try:
        return start_game(nxt)
    except GameError:
        # Leave the new game scheduled: phones (or Start game in dev tools) can start it.
        log.warning('Next game %s created but not started', nxt.id, exc_info=True)
        return Game.objects.get(pk=nxt.pk)


def start_preview(game):
    """Run both cameras without recording so a developer can calibrate before the game."""
    if game.status not in OPEN_STATUSES:
        raise GameError('Preview is for games that have not started. Calibrate a live game directly.')
    if not (game.camera_a_id and game.camera_b_id):
        raise GameError('Both players need to pick an end first.')
    if Game.objects.filter(status='live').exists():
        raise GameError('A game is live. Preview would interrupt it.', status=409)
    manager = require_manager()
    apply_detector_settings()
    try:
        manager.start_match(game.camera_a_id, game.camera_b_id, preview=True)
    except ValueError as exc:
        raise GameError(str(exc))
    return game


def stop_preview(game):
    manager = get_field_manager()
    if manager and (manager.in_preview(game.camera_a_id) or manager.in_preview(game.camera_b_id)):
        manager.stop_match()
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


def camera_for_end(game, end):
    return game.camera_a_id if end == 'end_a' else game.camera_b_id if end == 'end_b' else ''


# ------------------------------------------------------------------ segments
SEGMENT_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
MAX_SEGMENTS = 200


def clean_segments(raw):
    """Validate a client-sent segment list. Raises GameError on bad input."""
    if not isinstance(raw, list):
        raise GameError('segments must be a list.')
    if len(raw) > MAX_SEGMENTS:
        raise GameError(f'At most {MAX_SEGMENTS} segments per game.')
    out, seen = [], set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise GameError(f'Segment {i + 1} is not an object.')
        sid = str(s.get('id', ''))
        if not SEGMENT_ID_RE.match(sid) or sid in seen:
            raise GameError(f'Segment {i + 1} has a missing, invalid or duplicate id.')
        end = s.get('end')
        if end not in END_LABEL:
            raise GameError(f'Segment {i + 1}: end must be end_a or end_b.')
        try:
            start_s = round(float(s.get('start_s')), 3)
            end_s = round(float(s.get('end_s')), 3)
        except (TypeError, ValueError):
            raise GameError(f'Segment {i + 1}: start_s and end_s must be numbers.')
        if start_s < 0 or end_s <= start_s:
            raise GameError(f'Segment {i + 1}: end must be after start.')
        label = str(s.get('label') or f'Segment {i + 1}').strip()[:80]
        seen.add(sid)
        out.append({'id': sid, 'end': end, 'label': label, 'start_s': start_s, 'end_s': end_s})
    return out


def update_segments(game, raw):
    segments = clean_segments(raw)
    game.segments = segments
    # Forget analysis of segments that no longer exist.
    analysis = dict(game.analysis or {})
    if analysis.get('segments'):
        keep = {s['id'] for s in segments}
        analysis['segments'] = {k: v for k, v in analysis['segments'].items() if k in keep}
        game.analysis = analysis
    game.save(update_fields=['segments', 'analysis', 'updated_at'])
    return game


# ------------------------------------------------------------------ analysis
def analysis_dir(game):
    manager = require_manager()
    return Path(manager.data_dir) / 'analysis' / game.id


def segment_dir(game, seg):
    return analysis_dir(game) / camera_for_end(game, seg['end']) / 'segments' / seg['id']


def start_analysis(game, segment_ids=None, full=None):
    """Run the offline pipeline in a background thread.

    ``segment_ids`` None: the whole recording of each camera (as before).
    Otherwise only those segments, each over its own time range.
    ``full`` True also analyses the whole recordings alongside the segments (batch runs
    from data prep); it defaults to True only when no segments are given.
    """
    if full is None:
        full = segment_ids is None
    if game.status != 'completed':
        raise GameError('Only finished games can be analysed.')
    if game.analysis_status == 'running':
        raise GameError('Analysis is already running.', status=409)
    files = recording_files(game)
    if not files:
        raise GameError('This game has no recorded video to analyse.')
    segments = None
    if segment_ids is not None:
        by_id = {s['id']: s for s in (game.segments or [])}
        missing = [sid for sid in segment_ids if sid not in by_id]
        if missing or not segment_ids:
            raise GameError('Pick at least one existing segment to analyse.')
        segments = [by_id[sid] for sid in segment_ids]
        recorded = {cam for cam, _ in files}
        for seg in segments:
            if camera_for_end(game, seg['end']) not in recorded:
                raise GameError(f'{END_LABEL[seg["end"]]} has no recording for segment "{seg["label"]}".')
    out_root = analysis_dir(game)
    game.analysis_status = 'running'
    game.save(update_fields=['analysis_status', 'updated_at'])
    threading.Thread(target=_run_analysis, args=(game.id, files, out_root, segments, full), daemon=True).start()
    return game


def _calibrator_for(manager, camera_id):
    from src.calibration.homography import CourtCalibrator

    calib_path = manager.registry.calibration_path(camera_id) if manager else None
    if calib_path and calib_path.exists():
        return CourtCalibrator.load(calib_path)
    return None


def _run_full(game, manager, files, out_root):
    from src.pipeline import ClearPipeline

    results = {}
    for camera_id, path in files:
        if not path.exists():
            results[camera_id] = {'error': 'Recording file is missing.'}
            continue
        calib = _calibrator_for(manager, camera_id)
        end = 'end_a' if camera_id == game.camera_a_id else 'end_b'
        pipeline = ClearPipeline(calibrator=calib, court_mode=game.court_mode)
        report = pipeline.run_video(path, out_root / camera_id)
        report.pop('video_out_path', None)
        report.pop('annotated_video', None)
        results[end] = {'camera_id': camera_id, 'calibrated': calib is not None, **report}
    return results


def _run_segments(game, manager, files, segments):
    from src.pipeline import ClearPipeline

    from .media import video_info

    paths = dict(files)
    results = {}
    for seg in segments:
        camera_id = camera_for_end(game, seg['end'])
        path = paths.get(camera_id)
        base = {'end': seg['end'], 'camera_id': camera_id, 'label': seg['label'],
                'start_s': seg['start_s'], 'end_s': seg['end_s']}
        if not path or not path.exists():
            results[seg['id']] = {**base, 'error': 'Recording file is missing.'}
            continue
        fps = video_info(path)['fps']
        calib = _calibrator_for(manager, camera_id)
        pipeline = ClearPipeline(calibrator=calib, court_mode=game.court_mode)
        try:
            report = pipeline.run_video(
                path, segment_dir(game, seg),
                start_frame=int(round(seg['start_s'] * fps)),
                end_frame=int(round(seg['end_s'] * fps)),
            )
        except Exception as exc:
            log.exception('Segment %s of game %s failed', seg['id'], game.id)
            results[seg['id']] = {**base, 'error': str(exc)}
            continue
        report.pop('annotated_video', None)
        results[seg['id']] = {**base, 'calibrated': calib is not None,
                              'finished_at': timezone.now().isoformat(), **report}
    return results


def _run_analysis(game_id, files, out_root, segments=None, full=None):
    close_old_connections()
    try:
        game = Game.objects.get(id=game_id)
        manager = get_field_manager()
        analysis = dict(game.analysis or {})
        analysis.pop('error', None)
        if full is None:
            full = segments is None
        if full:
            analysis['cameras'] = _run_full(game, manager, files, out_root)
            analysis['finished_at'] = timezone.now().isoformat()
        if segments:
            done = dict(analysis.get('segments') or {})
            done.update(_run_segments(game, manager, files, segments))
            analysis['segments'] = done
        Game.objects.filter(id=game_id).update(analysis_status='done', analysis=analysis)
    except Exception as exc:  # surface any pipeline failure to the dev UI
        log.exception('Analysis failed for game %s', game_id)
        game = Game.objects.filter(id=game_id).first()
        analysis = dict((game.analysis if game else None) or {})
        analysis['error'] = str(exc)
        Game.objects.filter(id=game_id).update(analysis_status='failed', analysis=analysis)
    finally:
        close_old_connections()


# ------------------------------------------------------------------ export
def export_runs(game, segment_ids=None):
    """Runs to put in a data-export bundle.

    ``segment_ids`` None: every analysed run (full ends + segments); otherwise just those segments.
    """
    root = analysis_dir(game)
    players = [u.name if u else None for u in (game.connection.user_a, game.connection.user_b)]
    common = {
        'game_id': game.id,
        'game_title': game.title,
        'players': players,
        'court_mode': game.court_mode,
        'recording_id': game.recording_id,
        'game_started_at': game.started_at.isoformat() if game.started_at else None,
    }
    analysis = game.analysis or {}
    runs = []
    if segment_ids is None:
        for end, rep in (analysis.get('cameras') or {}).items():
            cam = rep.get('camera_id') or camera_for_end(game, end)
            runs.append({
                'dir': root / cam,
                'run_id': f'{end}_full',
                'meta': {**common, 'end': end, 'camera_id': cam, 'segment_id': None,
                         'label': f'{END_LABEL.get(end, end)} full recording',
                         'calibrated': rep.get('calibrated')},
            })
    by_id = {s['id']: s for s in (game.segments or [])}
    wanted = list(by_id) if segment_ids is None else segment_ids
    seg_reports = analysis.get('segments') or {}
    for sid in wanted:
        seg = by_id.get(sid)
        if not seg or sid not in seg_reports or seg_reports[sid].get('error'):
            continue
        runs.append({
            'dir': segment_dir(game, seg),
            'run_id': f'{seg["end"]}_{sid}',
            'meta': {**common, 'end': seg['end'], 'camera_id': camera_for_end(game, seg['end']),
                     'segment_id': sid, 'label': seg['label'],
                     'segment_start_s': seg['start_s'], 'segment_end_s': seg['end_s'],
                     'calibrated': seg_reports[sid].get('calibrated')},
        })
    return runs
