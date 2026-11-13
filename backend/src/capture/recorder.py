"""Camera recorder: writes raw + annotated MP4s per camera, plus recording sessions."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np


class CameraRecorder:
    """Writes one raw and one annotated MP4 for a single camera."""

    def __init__(self, camera_id: str, out_dir: Path, fps: float) -> None:
        self.camera_id = camera_id
        self.out_dir = out_dir
        self.fps = max(1.0, float(fps))
        self.raw_path = out_dir / f"{camera_id}_raw.mp4"
        self.annot_path = out_dir / f"{camera_id}_annot.mp4"
        self._raw_writer: Optional[cv2.VideoWriter] = None
        self._annot_writer: Optional[cv2.VideoWriter] = None
        self._size: Optional[tuple[int, int]] = None
        self.frame_count = 0
        self.lock = threading.Lock()

    def _ensure_writer(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        size = (w, h)
        if self._raw_writer is not None and size == self._size:
            return
        self._size = size
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._raw_writer = cv2.VideoWriter(str(self.raw_path), fourcc, self.fps, size)
        self._annot_writer = cv2.VideoWriter(str(self.annot_path), fourcc, self.fps, size)

    def write(self, raw_frame: np.ndarray, annotated: np.ndarray) -> None:
        with self.lock:
            self._ensure_writer(raw_frame)
            if self._raw_writer is not None and self._raw_writer.isOpened():
                self._raw_writer.write(raw_frame)
            if self._annot_writer is not None and self._annot_writer.isOpened():
                self._annot_writer.write(annotated)
            self.frame_count += 1

    def finalize(self) -> Dict[str, object]:
        with self.lock:
            if self._raw_writer is not None:
                self._raw_writer.release()
                self._raw_writer = None
            if self._annot_writer is not None:
                self._annot_writer.release()
                self._annot_writer = None
        files = []
        for name, path in (("raw", self.raw_path), ("annotated", self.annot_path)):
            if path.exists():
                files.append({"name": name, "filename": path.name, "bytes": path.stat().st_size})
        return {
            "camera_id": self.camera_id,
            "frames": self.frame_count,
            "files": files,
        }


class RecordingSession:
    """A named recording spanning one or more cameras."""

    def __init__(self, session_id: str, name: str, data_dir: Path, fps: float) -> None:
        self.id = session_id
        self.name = name
        self.data_dir = data_dir
        self.dir = data_dir / "recordings" / session_id
        self.fps = fps
        self.dir.mkdir(parents=True, exist_ok=True)
        self.recorders: Dict[str, CameraRecorder] = {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.meta_path = self.dir / "meta.json"

    def add_camera(self, camera_id: str) -> CameraRecorder:
        recorder = CameraRecorder(camera_id, self.dir, self.fps)
        self.recorders[camera_id] = recorder
        return recorder

    def finalize(self) -> Dict[str, object]:
        cameras = []
        for camera_id, recorder in self.recorders.items():
            cameras.append(recorder.finalize())
        meta = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "fps": self.fps,
            "cameras": cameras,
        }
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def load_meta(self) -> Dict[str, object]:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"id": self.id, "name": self.name, "cameras": []}

    def save_meta(self, meta: Dict[str, object]) -> None:
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def delete(self) -> None:
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)


def list_recordings(data_dir: Path) -> List[Dict[str, object]]:
    recordings: List[Dict[str, object]] = []
    root = data_dir / "recordings"
    if not root.exists():
        return recordings
    for meta_file in sorted(root.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        recordings.append(meta)
    return recordings


def get_recording(data_dir: Path, session_id: str) -> Optional[Dict[str, object]]:
    meta_file = data_dir / "recordings" / session_id / "meta.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
