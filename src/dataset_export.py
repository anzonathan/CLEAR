"""Build a labelling dataset (ZIP) from trimmed recording clips.

One *clip* is a frame range of one camera's recording: a whole end, or a segment a
developer trimmed. For each clip the bundle can hold the raw video, the overlay video,
sampled raw frames for labelling, YOLO pre-labels for those frames, the camera
calibration, the pipeline analysis and all game metadata. Layout::

    README.md
    manifest.json                     export options + one entry per clip
    clips.csv                         one row per clip
    frames.csv                        one row per sampled frame (which clip/frame/time)
    clips/<clip_id>/raw.mp4           H.264, exactly source frames [start_frame, end_frame)
    clips/<clip_id>/overlay.mp4       same frame range with the CLEAR overlay
    clips/<clip_id>/meta.json         game, players, camera, range, calibration, sources
    clips/<clip_id>/calibration.json  camera calibration as saved on the server
    clips/<clip_id>/analysis/...      pipeline outputs when this exact range was analysed
    roboflow/data.yaml                class names for the YOLO labels
    roboflow/images/<clip_id>_f<frame>.jpg
    roboflow/labels/<clip_id>_f<frame>.txt   YOLO pre-labels (normalised cx cy w h)

Frame numbers are always frames of the source recording, so frame N in frames.csv,
tracks.csv and the clip (at index N - start_frame) are the same image.

Upload ``roboflow/`` to Roboflow as a YOLO dataset: images and their pre-labels import
together and can be corrected there. Pre-labels come from the stock detector and are a
starting point only.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import shutil
import subprocess
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np

from src.analysis_export import add_run, code_version, safe_id

log = logging.getLogger(__name__)

DATASET_VERSION = 1
CLASSES = ["ball", "player", "racket"]
# Hard cap so a careless 30 fps sample of a long recording cannot fill the disk.
MAX_FRAMES_PER_CLIP = 3000
# The hybrid ball detector differences 3 consecutive frames.
DETECT_CONTEXT = 3

DEFAULT_OPTIONS = {
    "raw": True,
    "overlay": True,
    "frames_fps": 2.0,
    "prelabels": True,
    "analysis": True,
    "jpeg_quality": 92,
}

CLIP_COLUMNS = [
    "clip_id", "label", "game_id", "game_title", "players", "court_mode", "end", "camera_id",
    "segment_id", "start_s", "end_s", "start_frame", "end_frame", "fps", "width", "height",
    "frames_sampled", "raw", "overlay", "overlay_source", "analysis", "calibrated",
]
FRAME_COLUMNS = ["image", "clip_id", "frame_idx", "clip_frame", "t_s", "t_clip_s", "game_id", "end", "labels"]

Progress = Callable[[str], None]


def clean_options(raw: Optional[Dict[str, object]]) -> Dict[str, object]:
    """Merge client options over the defaults, clamped to sane values."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_OPTIONS)
    for k in ("raw", "overlay", "prelabels", "analysis"):
        if k in raw:
            out[k] = bool(raw[k])
    try:
        out["frames_fps"] = min(30.0, max(0.0, float(raw.get("frames_fps", out["frames_fps"]))))
    except (TypeError, ValueError):
        pass
    try:
        out["jpeg_quality"] = int(min(100, max(50, int(raw.get("jpeg_quality", out["jpeg_quality"])))))
    except (TypeError, ValueError):
        pass
    if out["frames_fps"] == 0:
        out["prelabels"] = False  # labels belong to sampled frames
    return out


def video_props(path: Path) -> Dict[str, float]:
    cap = cv2.VideoCapture(str(path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        return {
            "fps": fps,
            "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        }
    finally:
        cap.release()


def sample_frames(start: int, end: int, fps: float, frames_fps: float) -> List[int]:
    """Source frame numbers to save as images: every ``fps / frames_fps`` frames."""
    if frames_fps <= 0 or end <= start:
        return []
    step = max(1, int(round(fps / frames_fps)))
    out = list(range(start, end, step))
    if len(out) > MAX_FRAMES_PER_CLIP:
        stride = len(out) / MAX_FRAMES_PER_CLIP
        out = [out[int(i * stride)] for i in range(MAX_FRAMES_PER_CLIP)]
    return out


def yolo_lines(dets, width: int, height: int) -> List[str]:
    """YOLO label lines (class cx cy w h, normalised) for one frame's detections."""
    lines = []

    def box(cls, x1, y1, x2, y2):
        x1, x2 = max(0.0, min(x1, x2)), min(float(width), max(x1, x2))
        y1, y2 = max(0.0, min(y1, y2)), min(float(height), max(y1, y2))
        if x2 - x1 < 1 or y2 - y1 < 1:
            return
        cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
        lines.append(f"{cls} {cx:.6f} {cy:.6f} {(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")

    for b in dets.balls[:1]:  # one ball per frame: the detector's best guess
        half = max(3.0, float(b.radius)) + 2.0
        box(0, b.u - half, b.v - half, b.u + half, b.v + half)
    for p in dets.players:
        box(1, *p.bbox)
    for r in dets.rackets:
        box(2, *r.bbox)
    return lines


def _ffmpeg() -> Optional[str]:
    return os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")


def _to_h264(src: Path, dst: Path) -> str:
    """Re-encode an OpenCV mp4v file to H.264 (plays everywhere, Roboflow accepts it).

    Keeps every frame (no fps conversion) so clip frame k stays source frame start + k.
    Without a working ffmpeg the mp4v file is kept as-is. Returns the codec written.
    """
    ff = _ffmpeg()
    if not ff:
        src.replace(dst)
        return "mp4v"
    cmd = [
        ff, "-y", "-loglevel", "error", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-fps_mode", "passthrough", "-movflags", "+faststart", "-an", str(dst),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 60)
        ok = proc.returncode == 0
        err = proc.stderr.strip()[-300:]
    except (OSError, subprocess.SubprocessError) as exc:
        ok, err = False, str(exc)
    if not ok:
        log.warning("H.264 re-encode failed, keeping mp4v: %s", err)
        dst.unlink(missing_ok=True)
        src.replace(dst)
        return "mp4v"
    src.unlink(missing_ok=True)
    return "h264"


class _Writer:
    """Lazily opened mp4v writer (size known from the first frame)."""

    def __init__(self, path: Path, fps: float):
        self.path, self.fps, self.w, self.count = path, fps, None, 0

    def write(self, frame: np.ndarray):
        if self.w is None:
            h, w = frame.shape[:2]
            self.w = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
        self.w.write(frame)
        self.count += 1

    def close(self):
        if self.w is not None:
            self.w.release()


def cut_video(src: Path, start: int, end: int, dst: Path, fps: Optional[float] = None) -> int:
    """Copy source frames [start, end) to ``dst`` (H.264 when ffmpeg works). Returns frames written."""
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {src.name}")
    fps = fps or float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
    tmp = dst.with_name(dst.stem + ".mp4v.mp4")
    writer = _Writer(tmp, fps)
    try:
        if start > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        idx = start
        while idx < end:
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(frame)
            idx += 1
    finally:
        cap.release()
        writer.close()
    if writer.count == 0:
        tmp.unlink(missing_ok=True)
        return 0
    _to_h264(tmp, dst)
    return writer.count


def process_raw(
    src: Path,
    start: int,
    end: int,
    fps: float,
    samples: List[int],
    work: Path,
    clip_id: str,
    options: Dict[str, object],
    detector=None,
) -> Dict[str, object]:
    """One pass over the raw range: write the raw clip, sampled JPGs and YOLO pre-labels."""
    sample_set = set(samples)
    images_dir, labels_dir = work / "images", work / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    if detector is not None:
        labels_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {src.name}")
    # Read a few frames before the range so the first sample has detector context.
    read_from = max(0, start - (DETECT_CONTEXT - 1)) if detector is not None else start
    if read_from > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, read_from)
    writer = _Writer(work / "raw.mp4v.mp4", fps) if options.get("raw") else None
    recent: deque = deque(maxlen=DETECT_CONTEXT)
    frames: List[Dict[str, object]] = []
    quality = [int(cv2.IMWRITE_JPEG_QUALITY), int(options.get("jpeg_quality", 92))]
    idx = read_from
    size = (0, 0)
    try:
        while idx < end:
            ok, frame = cap.read()
            if not ok:
                break
            recent.append((idx, frame))
            if idx >= start:
                size = (frame.shape[1], frame.shape[0])
                if writer is not None:
                    writer.write(frame)
                if idx in sample_set:
                    name = f"{clip_id}_f{idx:06d}"
                    cv2.imwrite(str(images_dir / f"{name}.jpg"), frame, quality)
                    n_labels = None
                    if detector is not None:
                        detector.reset()
                        dets = None
                        for j, f in recent:
                            dets = detector.detect(f, j)
                        lines = yolo_lines(dets, frame.shape[1], frame.shape[0])
                        (labels_dir / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
                        n_labels = len(lines)
                    frames.append({
                        "image": f"{name}.jpg",
                        "clip_id": clip_id,
                        "frame_idx": idx,
                        "clip_frame": idx - start,
                        "t_s": round(idx / fps, 4),
                        "t_clip_s": round((idx - start) / fps, 4),
                        "labels": n_labels,
                    })
            idx += 1
    finally:
        cap.release()
        if writer is not None:
            writer.close()
    raw_frames = writer.count if writer is not None else None
    codec = None
    if writer is not None and writer.count:
        codec = _to_h264(work / "raw.mp4v.mp4", work / "raw.mp4")
    return {"frames": frames, "raw_frames": raw_frames, "end_read": idx, "size": size, "codec": codec}


def _write_csv(columns: List[str], rows: List[Dict[str, object]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return buf.getvalue().encode("utf-8")


def _readme(options: Dict[str, object], clips: int, frames: int) -> str:
    return f"""# CLEAR labelling dataset

{clips} clip(s), {frames} sampled frame(s). Built {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC
by CLEAR {code_version()}.

## Roboflow

Upload the `roboflow/` folder as a YOLO dataset (images + labels + data.yaml).
Classes: {", ".join(f"{i} = {c}" for i, c in enumerate(CLASSES))}.
{"Labels are PRE-LABELS from the stock detector: review every box before training." if options.get("prelabels") else "No pre-labels were generated: images import unlabelled."}

## Files

- `clips/<clip>/raw.mp4`: the camera recording, trimmed. Frame k = source frame start_frame + k.
- `clips/<clip>/overlay.mp4`: the same range with the CLEAR overlay (see `overlay_source` in meta.json:
  `analysis` = offline pipeline overlay, `live` = the overlay recorded during the game).
- `clips/<clip>/meta.json`: game, players, camera, calibration, frame range, sources.
- `clips/<clip>/analysis/`: pipeline outputs, only when exactly this range was analysed.
- `clips.csv`, `frames.csv`: flat indexes. `frame_idx` is always the source recording frame.
"""


def build_dataset(
    clips: List[Dict[str, object]],
    options: Dict[str, object],
    out_zip: Path,
    work_root: Path,
    export_meta: Optional[Dict[str, object]] = None,
    progress: Optional[Progress] = None,
) -> Dict[str, object]:
    """Build the dataset ZIP at ``out_zip``. Returns a summary for the job record.

    ``clips`` items (all paths absolute, missing ones None)::

        {clip_id, label, start_s, end_s, raw_path, live_overlay_path,
         analysis_dir, analysis_overlay_path, analysis_overlay_start_frame,
         calibration_path, meta: {...game / camera metadata...}}

    ``analysis_dir`` is set only when its run covers exactly this clip's range.
    ``analysis_overlay_start_frame`` is the source frame the analysis overlay video starts at.
    """
    options = clean_options(options)
    progress = progress or (lambda _msg: None)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    detector = None
    if options["prelabels"]:
        from src.detect.detector import HybridTennisDetector

        detector = HybridTennisDetector(mode="hybrid")

    entries: List[Dict[str, object]] = []
    frame_rows: List[Dict[str, object]] = []
    tmp_zip = out_zip.with_name(out_zip.stem + ".part.zip")
    stored, deflated = zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED

    with zipfile.ZipFile(tmp_zip, "w", compression=deflated, allowZip64=True) as zf:
        for n, clip in enumerate(clips, 1):
            clip_id = safe_id(str(clip["clip_id"]))
            progress(f"Clip {n}/{len(clips)}: {clip.get('label') or clip_id}")
            prefix = f"clips/{clip_id}"
            work = work_root / clip_id
            work.mkdir(parents=True, exist_ok=True)
            entry: Dict[str, object] = {"clip_id": clip_id, "label": clip.get("label"), **dict(clip.get("meta") or {})}
            try:
                raw_path = Path(clip["raw_path"]) if clip.get("raw_path") else None
                if raw_path is None or not raw_path.exists():
                    raise RuntimeError("Raw recording is missing on the server.")
                props = video_props(raw_path)
                fps = props["fps"]
                start = max(0, int(round(float(clip.get("start_s") or 0) * fps)))
                end_s = clip.get("end_s")
                end = props["frames"] if end_s is None else int(round(float(end_s) * fps))
                if props["frames"]:
                    end = min(end, props["frames"])
                if end <= start:
                    raise RuntimeError("Clip range is empty.")
                samples = sample_frames(start, end, fps, float(options["frames_fps"]))

                res = process_raw(raw_path, start, end, fps, samples, work, clip_id, options, detector)
                end = min(end, res["end_read"]) if res["end_read"] > start else end
                entry.update({
                    "start_s": round(start / fps, 3), "end_s": round(end / fps, 3),
                    "start_frame": start, "end_frame": end, "fps": round(fps, 3),
                    "width": res["size"][0] or props["width"], "height": res["size"][1] or props["height"],
                    "frames_sampled": len(res["frames"]),
                    "video_codec": res["codec"],
                })
                if (work / "raw.mp4").exists():
                    zf.write(work / "raw.mp4", f"{prefix}/raw.mp4", compress_type=stored)
                    entry["raw"] = f"{prefix}/raw.mp4"
                for fr in res["frames"]:
                    zf.write(work / "images" / fr["image"], f"roboflow/images/{fr['image']}", compress_type=stored)
                    if fr["labels"] is not None:
                        lbl = fr["image"][:-4] + ".txt"
                        zf.write(work / "labels" / lbl, f"roboflow/labels/{lbl}")
                    frame_rows.append({**fr, "game_id": entry.get("game_id"), "end": entry.get("end")})

                # Overlay: the offline analysis overlay when it covers the range, else the live one.
                entry["overlay_source"] = None
                if options["overlay"]:
                    progress(f"Clip {n}/{len(clips)}: overlay")
                    ov = Path(clip["analysis_overlay_path"]) if clip.get("analysis_overlay_path") else None
                    ov_start = int(clip.get("analysis_overlay_start_frame") or 0)
                    live = Path(clip["live_overlay_path"]) if clip.get("live_overlay_path") else None
                    written = 0
                    if ov is not None and ov.exists() and ov_start <= start:
                        written = cut_video(ov, start - ov_start, end - ov_start, work / "overlay.mp4", fps)
                        entry["overlay_source"] = "analysis" if written else None
                    if not written and live is not None and live.exists():
                        written = cut_video(live, start, end, work / "overlay.mp4", fps)
                        entry["overlay_source"] = "live" if written else None
                    if written:
                        zf.write(work / "overlay.mp4", f"{prefix}/overlay.mp4", compress_type=stored)
                        entry["overlay"] = f"{prefix}/overlay.mp4"

                cal_path = Path(clip["calibration_path"]) if clip.get("calibration_path") else None
                entry["calibrated"] = bool(cal_path and cal_path.exists())
                if entry["calibrated"]:
                    zf.write(cal_path, f"{prefix}/calibration.json")
                    try:
                        entry["calibration"] = json.loads(cal_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        entry["calibration"] = None

                entry["analysis"] = None
                adir = Path(clip["analysis_dir"]) if clip.get("analysis_dir") else None
                if options["analysis"] and adir is not None and (adir / "summary.json").exists():
                    add_run(zf, adir, f"{prefix}/analysis", {"clip_id": clip_id, **dict(clip.get("meta") or {})})
                    entry["analysis"] = f"{prefix}/analysis"
            except Exception as exc:  # one bad clip must not sink the whole export
                entry["error"] = str(exc)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            zf.writestr(f"{prefix}/meta.json", json.dumps(entry, indent=2, default=str))
            entries.append(entry)

        progress("Writing indexes")
        rows = [{**e, "players": " vs ".join(p or "?" for p in (e.get("players") or []))} for e in entries]
        zf.writestr("clips.csv", _write_csv(CLIP_COLUMNS, rows))
        zf.writestr("frames.csv", _write_csv(FRAME_COLUMNS, frame_rows))
        zf.writestr(
            "roboflow/data.yaml",
            "# CLEAR pre-labels. Review in Roboflow before training.\n"
            f"nc: {len(CLASSES)}\nnames: [{', '.join(CLASSES)}]\n",
        )
        manifest = {
            "dataset_version": DATASET_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "code_version": code_version(),
            "classes": CLASSES,
            "options": options,
            **(export_meta or {}),
            "clips": [{k: v for k, v in e.items() if k != "calibration"} for e in entries],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        zf.writestr("README.md", _readme(options, len(entries), len(frame_rows)))

    tmp_zip.replace(out_zip)
    shutil.rmtree(work_root, ignore_errors=True)
    return {
        "clips": len(entries),
        "failed_clips": sum(1 for e in entries if e.get("error")),
        "frames": len(frame_rows),
        "labelled_frames": sum(1 for f in frame_rows if f.get("labels")),
        "size_bytes": out_zip.stat().st_size,
    }
