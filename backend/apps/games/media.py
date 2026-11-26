"""Browser playback of game recordings.

Recordings are written by OpenCV with the ``mp4v`` (MPEG-4 Part 2) codec, which Chrome and
Safari cannot play. On first request each recording is converted once, in a background
thread, to an H.264 ``*_web.mp4`` next to it (faststart, so playback starts before the whole
file arrives). The web copy is reused until the source changes.
"""

import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

log = logging.getLogger(__name__)

KINDS = {'raw': '_raw.mp4', 'annotated': '_annot.mp4'}

_lock = threading.Lock()
_converting: dict[str, str] = {}  # web path -> 'running' | error message


def recording_path(manager, recording_id, camera_id, kind='raw'):
    """Path of one camera's raw/annotated recording, or None if it is not on disk."""
    if not (manager and recording_id and camera_id and kind in KINDS):
        return None
    path = Path(manager.data_dir) / 'recordings' / recording_id / f'{camera_id}{KINDS[kind]}'
    return path if path.exists() else None


def web_path(src: Path) -> Path:
    return src.with_name(src.stem + '_web.mp4')


def ffmpeg_bin():
    return os.getenv('FFMPEG_BIN') or shutil.which('ffmpeg')


def video_info(src: Path):
    """fps / frame count / size / duration of a video (read with OpenCV, no ffprobe needed)."""
    import cv2

    cap = cv2.VideoCapture(str(src))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()
    return {
        'fps': round(fps, 3),
        'frames': frames,
        'width': w,
        'height': h,
        'duration_s': round(frames / fps, 3) if fps else 0.0,
    }


def _is_fresh(src: Path, dst: Path) -> bool:
    return dst.exists() and dst.stat().st_size > 0 and dst.stat().st_mtime >= src.stat().st_mtime


def _convert(src: Path, dst: Path):
    tmp = dst.with_name(dst.stem + '.part.mp4')
    cmd = [
        ffmpeg_bin(), '-y', '-loglevel', 'error', '-i', str(src),
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
        # Keep every source frame at its original timestamp so frame N in the browser is
        # frame N in the pipeline (segment times map 1:1 to analysis frames).
        '-fps_mode', 'passthrough', '-g', '30',
        '-movflags', '+faststart', '-an', str(tmp),
    ]
    key = str(dst)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 60)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[-500:] or f'ffmpeg exited {proc.returncode}')
        tmp.replace(dst)
        with _lock:
            _converting.pop(key, None)
    except Exception as exc:  # reported to the client by prepare()
        log.exception('Web conversion failed for %s', src)
        tmp.unlink(missing_ok=True)
        with _lock:
            _converting[key] = f'Conversion failed: {exc}'


def prepare(src: Path):
    """Ensure a browser-playable copy exists. Returns {'state': 'ready'|'converting'|'error', ...}."""
    dst = web_path(src)
    if _is_fresh(src, dst):
        return {'state': 'ready'}
    if not ffmpeg_bin():
        return {'state': 'error', 'error': 'ffmpeg is not installed on the server.'}
    key = str(dst)
    with _lock:
        status = _converting.get(key)
        if status == 'running':
            return {'state': 'converting'}
        if status:  # previous failure: report once, allow retry on the next call
            _converting.pop(key, None)
            return {'state': 'error', 'error': status}
        _converting[key] = 'running'
    threading.Thread(target=_convert, args=(src, dst), daemon=True).start()
    return {'state': 'converting'}


_RANGE_RE = re.compile(r'bytes=(\d*)-(\d*)')
_CHUNK = 512 * 1024


def _iter_file(path: Path, start: int, length: int):
    with path.open('rb') as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            data = fh.read(min(_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def ranged_file_response(request, path: Path, content_type='video/mp4'):
    """Serve a file honouring HTTP Range, which <video> needs to seek."""
    size = path.stat().st_size
    header = request.headers.get('Range', '')
    m = _RANGE_RE.fullmatch(header.strip()) if header else None
    if not m or (not m.group(1) and not m.group(2)):
        resp = FileResponse(path.open('rb'), content_type=content_type)
        resp['Accept-Ranges'] = 'bytes'
        resp['Content-Length'] = str(size)
        return resp

    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  # suffix range: last N bytes
        start = max(0, size - int(m.group(2)))
        end = size - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        resp = HttpResponse(status=416)
        resp['Content-Range'] = f'bytes */{size}'
        return resp

    length = end - start + 1
    resp = StreamingHttpResponse(_iter_file(path, start, length), status=206, content_type=content_type)
    resp['Content-Range'] = f'bytes {start}-{end}/{size}'
    resp['Content-Length'] = str(length)
    resp['Accept-Ranges'] = 'bytes'
    return resp
