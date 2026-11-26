"""Data prep: batch analysis and labelling-dataset exports across games.

A *clip* selection is ``{game_id, end, segment_id}``; ``segment_id`` None means the whole
recording of that end. Exports run one at a time in a background thread and write a ZIP
under <field data dir>/exports/ (format: ``src.dataset_export``).
"""

import logging
import shutil
import threading
from pathlib import Path

from django.db import close_old_connections
from django.utils import timezone

from . import media, services
from .models import DatasetExport, Game
from .services import END_LABEL, GameError

log = logging.getLogger(__name__)

MAX_CLIPS = 500
ANALYSIS_OVERLAY = 'annotated_rally.mp4'

# One export at a time: each decodes and re-encodes video, and they share the CPU with
# live games. Ids of jobs this process owns, to spot ones orphaned by a restart.
_run_lock = threading.Lock()
_active: set[str] = set()
_active_lock = threading.Lock()


def exports_dir():
    return Path(services.require_manager().data_dir) / 'exports'


def export_path(export):
    return exports_dir() / f'{export.id}.zip'


# ------------------------------------------------------------------ selection
def clean_selection(raw):
    """Validate ``[{game_id, end, segment_id|null}]``; dedupe, keep order."""
    if not isinstance(raw, list) or not raw:
        raise GameError('Pick at least one clip.')
    if len(raw) > MAX_CLIPS:
        raise GameError(f'At most {MAX_CLIPS} clips per batch.')
    out, seen = [], set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise GameError(f'Clip {i + 1} is not an object.')
        gid, end = str(c.get('game_id') or ''), c.get('end')
        sid = c.get('segment_id') or None
        if not gid or end not in END_LABEL:
            raise GameError(f'Clip {i + 1} needs a game_id and an end (end_a or end_b).')
        key = (gid, end, sid)
        if key not in seen:
            seen.add(key)
            out.append({'game_id': gid, 'end': end, 'segment_id': None if sid is None else str(sid)})
    return out


def _games_for(selection):
    ids = {c['game_id'] for c in selection}
    games = Game.objects.filter(id__in=ids).select_related('connection__user_a', 'connection__user_b')
    by_id = {g.id: g for g in games}
    missing = ids - set(by_id)
    if missing:
        raise GameError(f'Unknown game(s): {", ".join(sorted(missing))}', status=404)
    for g in by_id.values():
        if g.status != 'completed' or not g.recording_id:
            raise GameError(f'"{g}" has no finished recording.')
    return by_id


def _segment(game, sid):
    seg = next((s for s in (game.segments or []) if s['id'] == sid), None)
    if seg is None:
        raise GameError(f'"{game}" has no segment {sid}. It may have been deleted.', status=404)
    return seg


# ------------------------------------------------------------------ batch analysis
def start_batch_analysis(raw_selection):
    """Start analysis for every selected clip, one background run per game.

    Returns ``{'started': [game ids], 'errors': {game_id: message}}``. A game already
    being analysed is reported, not queued.
    """
    selection = clean_selection(raw_selection)
    games = _games_for(selection)
    plan = {}
    for c in selection:
        p = plan.setdefault(c['game_id'], {'full': False, 'segments': []})
        if c['segment_id'] is None:
            p['full'] = True
        else:
            _segment(games[c['game_id']], c['segment_id'])
            if c['segment_id'] not in p['segments']:
                p['segments'].append(c['segment_id'])
    started, errors = [], {}
    for gid, p in plan.items():
        try:
            services.start_analysis(games[gid], segment_ids=p['segments'] or None, full=p['full'])
            started.append(gid)
        except GameError as exc:
            errors[gid] = str(exc)
    return {'started': started, 'errors': errors}


# ------------------------------------------------------------------ export
def _clip_spec(game, sel, manager):
    """Everything build_dataset needs for one selected clip (paths resolved on this server)."""
    end, sid = sel['end'], sel['segment_id']
    cam = services.camera_for_end(game, end)
    raw = media.recording_path(manager, game.recording_id, cam, 'raw')
    live = media.recording_path(manager, game.recording_id, cam, 'annotated')
    analysis = game.analysis or {}
    full_dir = services.analysis_dir(game) / cam if cam else None
    full_done = end in (analysis.get('cameras') or {}) and not (analysis['cameras'][end] or {}).get('error')

    meta = {
        'game_id': game.id,
        'game_title': game.title,
        'players': [u.name if u else None for u in (game.connection.user_a, game.connection.user_b)],
        'court_mode': game.court_mode,
        'dev_mode': game.dev_mode,
        'recording_id': game.recording_id,
        'game_started_at': game.started_at.isoformat() if game.started_at else None,
        'game_ended_at': game.ended_at.isoformat() if game.ended_at else None,
        'end': end,
        'end_label': END_LABEL[end],
        'camera_id': cam,
        'segment_id': sid,
    }
    spec = {
        'raw_path': raw,
        'live_overlay_path': live,
        'calibration_path': manager.registry.calibration_path(cam) if cam else None,
        'analysis_dir': None,
        'analysis_overlay_path': None,
        'analysis_overlay_start_frame': 0,
        'meta': meta,
    }
    full_overlay = full_dir / ANALYSIS_OVERLAY if full_done and full_dir else None

    if sid is None:
        spec.update(clip_id=f'{game.id[:8]}_{end}_full', label=f'{game} · {END_LABEL[end]} full',
                    start_s=0, end_s=None)
        if full_done:
            spec['analysis_dir'] = full_dir
            spec['analysis_overlay_path'] = full_overlay
        return spec

    seg = _segment(game, sid)
    meta['segment_label'] = seg['label']
    spec.update(clip_id=f'{game.id[:8]}_{end}_{sid}', label=f'{game} · {seg["label"]}',
                start_s=seg['start_s'], end_s=seg['end_s'])
    seg_report = (analysis.get('segments') or {}).get(sid) or {}
    seg_dir = services.segment_dir(game, seg)
    if seg_report and not seg_report.get('error') and (seg_dir / 'summary.json').exists():
        # The segment run covers exactly this range; its overlay starts at the segment start.
        spec['analysis_dir'] = seg_dir
        spec['analysis_overlay_path'] = seg_dir / ANALYSIS_OVERLAY
        fps = media.video_info(raw)['fps'] if raw else 30.0
        spec['analysis_overlay_start_frame'] = int(round(seg['start_s'] * fps))
    elif full_overlay is not None:
        spec['analysis_overlay_path'] = full_overlay  # overlay only; the analysis covers more
    return spec


def create_export(user, raw_selection, options, name=''):
    from src.dataset_export import clean_options

    selection = clean_selection(raw_selection)
    games = _games_for(selection)
    for c in selection:
        if c['segment_id'] is not None:
            _segment(games[c['game_id']], c['segment_id'])
    services.require_manager()
    export = DatasetExport.objects.create(
        name=(name or '').strip()[:120] or f'{len(selection)} clip(s) · {timezone.now():%d %b %H:%M}',
        created_by=user, clips=selection, options=clean_options(options),
    )
    with _active_lock:
        _active.add(export.id)
    threading.Thread(target=_run_export, args=(export.id,), daemon=True).start()
    return export


def _set(export_id, **fields):
    DatasetExport.objects.filter(id=export_id).update(**fields)


def _run_export(export_id):
    close_old_connections()
    try:
        with _run_lock:
            export = DatasetExport.objects.get(id=export_id)
            _set(export_id, status='running', progress='Preparing clips')
            from src.dataset_export import build_dataset

            manager = services.require_manager()
            games = Game.objects.filter(id__in={c['game_id'] for c in export.clips}).select_related(
                'connection__user_a', 'connection__user_b'
            )
            by_id = {g.id: g for g in games}
            specs = []
            for sel in export.clips:
                game = by_id.get(sel['game_id'])
                if game is None:
                    continue
                try:
                    specs.append(_clip_spec(game, sel, manager))
                except GameError as exc:
                    log.warning('Export %s: skipped %s: %s', export_id, sel, exc)
            out = export_path(export)
            result = build_dataset(
                specs, export.options, out, exports_dir() / f'{export.id}_work',
                export_meta={'export_id': export.id, 'name': export.name, 'selection': export.clips},
                progress=lambda msg: _set(export_id, progress=msg[:200]),
            )
            result['skipped'] = len(export.clips) - len(specs)
            _set(export_id, status='done', progress='', result=result, finished_at=timezone.now())
    except Exception as exc:
        log.exception('Dataset export %s failed', export_id)
        _set(export_id, status='failed', error=str(exc)[:2000], progress='', finished_at=timezone.now())
    finally:
        with _active_lock:
            _active.discard(export_id)
        close_old_connections()


def reap_orphans():
    """Mark exports that were running when the server restarted as failed."""
    with _active_lock:
        active = set(_active)
    DatasetExport.objects.filter(status__in=['queued', 'running']).exclude(id__in=active).update(
        status='failed', error='The server restarted while this export was running. Start it again.',
        progress='', finished_at=timezone.now(),
    )


def delete_export(export):
    if export.status in ('queued', 'running'):
        raise GameError('This export is still running.', status=409)
    try:
        export_path(export).unlink(missing_ok=True)
        shutil.rmtree(exports_dir() / f'{export.id}_work', ignore_errors=True)
    except GameError:
        pass  # camera service down: drop the record anyway
    export.delete()


def selection_options():
    """Default export options for the UI."""
    from src.dataset_export import CLASSES, DEFAULT_OPTIONS, MAX_FRAMES_PER_CLIP

    return {'options': DEFAULT_OPTIONS, 'classes': CLASSES, 'max_frames_per_clip': MAX_FRAMES_PER_CLIP}
