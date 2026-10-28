"""Persistent field-camera registry.

The registry deliberately contains no inference state. It stores only channel
definitions and per-camera settings so the API can be restarted without losing
the field setup.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


SOURCES = ("browser", "rtsp")
CALIB_METHODS = ("manual", "auto", "segmentation")
COURT_MODES = ("singles", "doubles")


class CameraRegistry:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "cameras.json"
        self._lock = threading.RLock()
        self._cameras: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = []
        if isinstance(raw, dict):
            raw = list(raw.values())
        if not isinstance(raw, list):
            raw = []
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                self._cameras[str(item["id"])] = self._normalise(item)

    @staticmethod
    def _normalise(item: Dict[str, object]) -> Dict[str, object]:
        source = str(item.get("source", "browser"))
        if source not in SOURCES:
            source = "browser"
        overlays = item.get("overlays") if isinstance(item.get("overlays"), dict) else {}
        detector = item.get("detector") if isinstance(item.get("detector"), dict) else {}
        return {
            "id": str(item.get("id")),
            "name": str(item.get("name") or "Untitled camera"),
            "source": source,
            "rtsp_url": str(item.get("rtsp_url") or ""),
            "token": str(item.get("token") or secrets.token_urlsafe(24)),
            "court_mode": str(item.get("court_mode") or "singles"),
            "calib_method": str(item.get("calib_method") or "manual"),
            "created_at": float(item.get("created_at") or time.time()),
            "overlays": {
                "person": bool(overlays.get("person", True)),
                "racket": bool(overlays.get("racket", True)),
                "ball": bool(overlays.get("ball", True)),
                "court": bool(overlays.get("court", True)),
                "anchors": bool(overlays.get("anchors", False)),
            },
            "detector": {
                "person": _clamp(item.get("person", detector.get("person", 0.35)), 0.05, 0.95),
                "racket": _clamp(item.get("racket", detector.get("racket", 0.25)), 0.05, 0.95),
                "ball": _clamp(item.get("ball", detector.get("ball", 0.18)), 0.05, 0.95),
            },
        }

    def _save(self) -> None:
        payload = sorted(self._cameras.values(), key=lambda c: float(c.get("created_at", 0)))
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> List[Dict[str, object]]:
        with self._lock:
            return [dict(c) for c in sorted(self._cameras.values(), key=lambda c: float(c.get("created_at", 0)))]

    def get(self, camera_id: str) -> Optional[Dict[str, object]]:
        with self._lock:
            item = self._cameras.get(camera_id)
            return dict(item) if item else None

    def create(self, name: str, source: str, rtsp_url: str = "") -> Dict[str, object]:
        source = source if source in SOURCES else "browser"
        with self._lock:
            camera = self._normalise(
                {
                    "id": f"cam_{secrets.token_hex(5)}",
                    "name": name.strip() or "Untitled camera",
                    "source": source,
                    "rtsp_url": rtsp_url.strip(),
                    "token": secrets.token_urlsafe(24),
                    "created_at": time.time(),
                }
            )
            self._cameras[str(camera["id"])] = camera
            self._save()
            return dict(camera)

    def update(self, camera_id: str, **changes: object) -> Optional[Dict[str, object]]:
        with self._lock:
            current = self._cameras.get(camera_id)
            if current is None:
                return None
            merged = dict(current)
            for key in ("name", "source", "rtsp_url", "court_mode", "calib_method"):
                if key in changes and changes[key] is not None:
                    merged[key] = changes[key]
            if "overlays" in changes and isinstance(changes["overlays"], dict):
                merged["overlays"] = {**merged.get("overlays", {}), **changes["overlays"]}
            if "detector" in changes and isinstance(changes["detector"], dict):
                merged["detector"] = {**merged.get("detector", {}), **changes["detector"]}
            self._cameras[camera_id] = self._normalise(merged)
            self._save()
            return dict(self._cameras[camera_id])

    def delete(self, camera_id: str) -> bool:
        with self._lock:
            existed = self._cameras.pop(camera_id, None) is not None
            if existed:
                self._save()
            return existed

    def calibration_path(self, camera_id: str) -> Path:
        return self.data_dir / "cameras" / camera_id / "calib.json"

    def session_dir(self, camera_id: str) -> Path:
        path = self.data_dir / "sessions" / camera_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def token_matches(self, camera_id: str, token: str) -> bool:
        camera = self.get(camera_id)
        return bool(camera and token and secrets.compare_digest(str(camera["token"]), token))


def _clamp(value: object, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return round(max(low, min(high, number)), 2)
