"""Live field-camera runtime: one active channel at a time.

Design constraints:
- A Coolify VPS/GPU tower should not decode and infer every configured camera.
- Activating a channel stops the previous capture + inference worker.
- Frames are latest-value only. Stale frames are dropped, never queued.
- The same annotated JPEG is shared by every viewer of the active channel.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.calibration.auto_court import anchors_from_quad, detect_court_quad
from src.calibration.court_geometry import COURT_LINES_M, SPEC
from src.calibration.court_seg import detect_court_with_segmentation
from src.calibration.homography import CourtCalibrator
from src.capture.registry import CameraRegistry
from src.detect.detector import FrameDetections, HybridTennisDetector


ROOT = Path(__file__).resolve().parents[2]


class FieldCameraRuntime:
    def __init__(self, camera: Dict[str, object], data_dir: Path) -> None:
        self.camera = camera
        self.camera_id = str(camera["id"])
        self.data_dir = data_dir
        self.name = str(camera["name"])
        self.source = str(camera["source"])
        self.rtsp_url = str(camera.get("rtsp_url") or "")
        self.max_width = int(os.getenv("CLEAR_FIELD_MAX_WIDTH", "960"))
        self.target_fps = max(1.0, float(os.getenv("CLEAR_FIELD_TARGET_FPS", "15")))
        self.jpeg_quality = int(os.getenv("CLEAR_FIELD_JPEG_QUALITY", "72"))
        self.weights = os.getenv("CLEAR_YOLO_WEIGHTS", "models/yolov8n.pt")
        if not Path(self.weights).exists():
            self.weights = "yolov8n.pt"
        self.imgsz = int(os.getenv("CLEAR_YOLO_IMGSZ", "640"))
        self.device = os.getenv("CLEAR_DEVICE", "auto")
        self.detector_mode = os.getenv("CLEAR_DETECTOR_MODE", "hybrid")
        self.seg_weights = os.getenv("CLEAR_COURT_SEG_WEIGHTS", "")

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.raw_frame: Optional[np.ndarray] = None
        self.raw_seq = 0
        self.processed_seq = -1
        self.latest_jpeg: Optional[bytes] = None
        self.frame_index = 0
        self.ball_trail: Deque[Tuple[float, float]] = deque(maxlen=24)
        self.calibrator: Optional[CourtCalibrator] = None
        self.detector: Optional[HybridTennisDetector] = None
        self.reader_thread: Optional[threading.Thread] = None
        self.process_thread: Optional[threading.Thread] = None
        self.last_frame_ts = 0.0
        self.last_ingest_ts = 0.0
        self.ingest_connected = False
        self.fps = 0.0
        self.inference_ms = 0.0
        self.detections = {"person": 0, "racket": 0, "ball": 0}
        self.last_detections: Optional[FrameDetections] = None
        self.viewers = 0
        self.started_at = time.time()
        self.last_log_ts = 0.0

    # ------------------------------------------------------------------ setup
    def start(self) -> None:
        calib_path = self.data_dir / "cameras" / self.camera_id / "calib.json"
        if calib_path.exists():
            try:
                self.calibrator = CourtCalibrator.load(calib_path)
            except Exception:
                self.calibrator = None

        self.detector = HybridTennisDetector(
            mode=self.detector_mode,  # type: ignore[arg-type]
            yolo_weights=self.weights,
            ball_conf_thresh=float(self.camera["detector"]["ball"]),  # type: ignore[index]
            player_conf_thresh=float(self.camera["detector"]["person"]),  # type: ignore[index]
            racket_conf_thresh=float(self.camera["detector"]["racket"]),  # type: ignore[index]
            use_3frame_temporal=True,
            device=self.device,
            imgsz=self.imgsz,
        )
        self.stop_event.clear()
        if self.source == "rtsp":
            self.reader_thread = threading.Thread(target=self._rtsp_loop, name=f"rtsp-{self.camera_id}", daemon=True)
            self.reader_thread.start()
        self.process_thread = threading.Thread(target=self._process_loop, name=f"infer-{self.camera_id}", daemon=True)
        self.process_thread.start()
        self._log_event("activate", {"source": self.source})

    def stop(self) -> None:
        self.stop_event.set()
        for thread in (self.reader_thread, self.process_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)
        self.reader_thread = None
        self.process_thread = None
        self._log_event("deactivate", {})

    # ------------------------------------------------------------------ ingest
    def submit_frame(self, frame_bgr: np.ndarray) -> None:
        frame = _resize_max_width(frame_bgr, self.max_width)
        with self.lock:
            self.raw_frame = frame
            self.raw_seq += 1
            self.last_ingest_ts = time.time()
            self.last_frame_ts = self.last_ingest_ts

    def submit_jpeg(self, payload: bytes) -> bool:
        arr = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return False
        self.submit_frame(frame)
        return True

    def heartbeat(self) -> None:
        with self.lock:
            self.last_ingest_ts = time.time()
            self.ingest_connected = True

    def set_ingest_connected(self, connected: bool) -> None:
        with self.lock:
            self.ingest_connected = bool(connected)
            if connected:
                self.last_ingest_ts = time.time()

    def set_calibrator(self, calibrator: Optional[CourtCalibrator]) -> None:
        with self.lock:
            self.calibrator = calibrator

    # ------------------------------------------------------------------ capture
    def _rtsp_loop(self) -> None:
        if not self.rtsp_url:
            return
        cap: Optional[cv2.VideoCapture] = None
        while not self.stop_event.is_set():
            if cap is None or not cap.isOpened():
                try:
                    cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    cap = None
                if cap is None or not cap.isOpened():
                    time.sleep(1.0)
                    continue
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                cap = None
                time.sleep(0.5)
                continue
            self.submit_frame(frame)
            # Keep the capture side from racing ahead of inference.
            time.sleep(0.005)
        if cap is not None:
            cap.release()

    # ------------------------------------------------------------------ inference
    def _process_loop(self) -> None:
        last_tick = time.perf_counter()
        while not self.stop_event.is_set():
            with self.lock:
                frame = None if self.raw_frame is None else self.raw_frame.copy()
                seq = self.raw_seq
                cal = self.calibrator
                camera = dict(self.camera)
            if frame is None or seq == self.processed_seq:
                time.sleep(0.010)
                continue

            start = time.perf_counter()
            dets = FrameDetections(frame_idx=self.frame_index)
            try:
                if self.detector is not None:
                    dets = self.detector.detect(frame, frame_idx=self.frame_index, calibrator=cal)
            except Exception:
                dets = FrameDetections(frame_idx=self.frame_index)
            self.frame_index += 1
            self.processed_seq = seq
            annotated = self._render(frame, dets, camera, cal)
            ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
            jpeg = buf.tobytes() if ok else None
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            now = time.perf_counter()
            dt = max(1e-6, now - last_tick)
            last_tick = now
            inst_fps = 1.0 / dt
            with self.lock:
                self.latest_jpeg = jpeg
                self.inference_ms = round(0.85 * self.inference_ms + 0.15 * elapsed_ms, 1)
                self.fps = round(0.85 * self.fps + 0.15 * inst_fps, 1) if self.fps else round(inst_fps, 1)
                self.detections = {
                    "person": len(dets.players),
                    "racket": len(dets.rackets),
                    "ball": len(dets.balls),
                }
                self.last_detections = dets
                if dets.balls:
                    self.ball_trail.append((dets.balls[0].u, dets.balls[0].v))
                else:
                    self.ball_trail.clear()

            if time.time() - self.last_log_ts > 5.0 and self.frame_index % 5 == 0:
                self.last_log_ts = time.time()
                self._log_event(
                    "detections",
                    {
                        "frame_index": self.frame_index,
                        "counts": self.detections,
                        "fps": self.fps,
                        "inference_ms": self.inference_ms,
                    },
                )

            # Bound the loop to target FPS without building a backlog.
            if elapsed_ms < (1000.0 / self.target_fps):
                time.sleep(max(0.0, (1000.0 / self.target_fps - elapsed_ms) / 1000.0))

    # ------------------------------------------------------------------ render
    def _render(
        self,
        frame: np.ndarray,
        dets: FrameDetections,
        camera: Dict[str, object],
        cal: Optional[CourtCalibrator],
    ) -> np.ndarray:
        out = frame.copy()
        overlays = camera.get("overlays", {}) if isinstance(camera.get("overlays"), dict) else {}
        court_mode = str(camera.get("court_mode") or "singles")

        if overlays.get("court", True) and cal is not None and cal.H_court_to_img is not None:
            out = self._draw_court(out, cal, court_mode, bool(overlays.get("anchors", False)))

        if overlays.get("person", True):
            for p in dets.players:
                _draw_box(out, p.bbox, (255, 190, 40), f"PLAYER {p.conf:.2f}", 2)
                fu, fv = int(round(p.foot_uv[0])), int(round(p.foot_uv[1]))
                cv2.circle(out, (fu, fv), 4, (255, 190, 40), -1, cv2.LINE_AA)

        if overlays.get("racket", True):
            for r in dets.rackets:
                _draw_box(out, r.bbox, (210, 95, 255), f"RACKET {r.conf:.2f}", 2)

        if overlays.get("ball", True):
            pts = list(self.ball_trail)
            for i in range(1, len(pts)):
                alpha = i / max(1, len(pts))
                cv2.line(
                    out,
                    (int(pts[i - 1][0]), int(pts[i - 1][1])),
                    (int(pts[i][0]), int(pts[i][1])),
                    (0, int(170 * alpha), int(230 * alpha)),
                    max(1, int(3 * alpha)),
                    cv2.LINE_AA,
                )
            for b in dets.balls:
                radius = max(4, int(round(b.radius + 3)))
                cv2.circle(out, (int(b.u), int(b.v)), radius, (40, 245, 255), 2, cv2.LINE_AA)
                cv2.circle(out, (int(b.u), int(b.v)), 2, (255, 255, 255), -1, cv2.LINE_AA)

        self._draw_hud(out, camera, cal, dets)
        return out

    def _draw_court(
        self,
        frame: np.ndarray,
        cal: CourtCalibrator,
        court_mode: str,
        show_anchors: bool,
    ) -> np.ndarray:
        out = frame
        # Subtle active-court tint.
        if court_mode == "doubles":
            x1, x2 = 0.0, SPEC.doubles_width_m
        else:
            x1, x2 = SPEC.alley_width_m, SPEC.doubles_width_m - SPEC.alley_width_m
        poly_m = [[x1, 0.0], [x2, 0.0], [x2, SPEC.length_m], [x1, SPEC.length_m]]
        poly_px = np.round(cal.court_to_image(poly_m)).astype(np.int32)
        overlay = out.copy()
        cv2.fillPoly(overlay, [poly_px], (40, 80, 160))
        out = cv2.addWeighted(overlay, 0.08, out, 0.92, 0)

        for name, p1_m, p2_m, category in COURT_LINES_M:
            pts = cal.court_to_image([p1_m, p2_m])
            pt1 = (int(round(pts[0, 0])), int(round(pts[0, 1])))
            pt2 = (int(round(pts[1, 0])), int(round(pts[1, 1])))
            if category == "net":
                color, thickness = (255, 220, 110), 2
            elif category == "doubles" and court_mode == "singles":
                color, thickness = (155, 175, 190), 1
            else:
                color, thickness = (245, 250, 250), 2
            cv2.line(out, pt1, pt2, color, thickness, cv2.LINE_AA)

        if show_anchors:
            for point in cal.anchors_px.values():
                cv2.circle(out, (int(point[0]), int(point[1])), 7, (0, 210, 255), 2, cv2.LINE_AA)
                cv2.circle(out, (int(point[0]), int(point[1])), 2, (255, 255, 255), -1, cv2.LINE_AA)
        return out

    def _draw_hud(
        self,
        frame: np.ndarray,
        camera: Dict[str, object],
        cal: Optional[CourtCalibrator],
        dets: FrameDetections,
    ) -> None:
        h, w = frame.shape[:2]
        band = frame.copy()
        cv2.rectangle(band, (0, 0), (w, 38), (10, 15, 23), -1)
        cv2.addWeighted(band, 0.72, frame, 0.28, 0, frame)

        cv2.circle(frame, (18, 19), 6, (60, 70, 255), -1, cv2.LINE_AA)
        cv2.putText(frame, "LIVE", (32, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (245, 248, 252), 1, cv2.LINE_AA)
        title = str(camera.get("name", self.name))[:36]
        cv2.putText(frame, title, (88, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (245, 248, 252), 1, cv2.LINE_AA)

        status = f"{self.fps:.1f} FPS  |  {self.inference_ms:.0f} ms  |  {self.device.upper()}"
        (tw, _), _ = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1)
        cv2.putText(
            frame,
            status,
            (w - tw - 14, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (210, 225, 240),
            1,
            cv2.LINE_AA,
        )

        counts = f"P {len(dets.players)}   R {len(dets.rackets)}   B {len(dets.balls)}"
        (cw, _), _ = cv2.getTextSize(counts, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1)
        cv2.putText(
            frame,
            counts,
            (w - cw - 14, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (40, 245, 255),
            1,
            cv2.LINE_AA,
        )

        if cal is None or cal.H_court_to_img is None:
            text = "NO COURT CALIBRATION - open Calibration"
            (tw2, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            cv2.rectangle(frame, (12, h - 38), (tw2 + 24, h - 10), (18, 22, 28), -1)
            cv2.putText(
                frame,
                text,
                (18, h - 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (0, 215, 255),
                1,
                cv2.LINE_AA,
            )

        stamp = datetime.now().strftime("%H:%M:%S")
        (sw, _), _ = cv2.getTextSize(stamp, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
        cv2.putText(
            frame,
            stamp,
            (w - sw - 14, h - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (220, 230, 240),
            1,
            cv2.LINE_AA,
        )

    # ------------------------------------------------------------------ logs
    def _log_event(self, event: str, payload: Dict[str, object]) -> None:
        try:
            session_dir = self.data_dir / "sessions" / self.camera_id
            session_dir.mkdir(parents=True, exist_ok=True)
            line = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "camera_id": self.camera_id,
                "camera_name": self.name,
                "event": event,
                **payload,
            }
            with (session_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line) + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ stats
    def snapshot_jpeg(self, raw: bool = False) -> Optional[bytes]:
        with self.lock:
            if raw:
                if self.raw_frame is None:
                    return None
                ok, buf = cv2.imencode(".jpg", self.raw_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                return buf.tobytes() if ok else None
            return self.latest_jpeg

    def stats(self) -> Dict[str, object]:
        with self.lock:
            cal_ready = self.calibrator is not None and self.calibrator.H_court_to_img is not None
            resolution = None
            if self.raw_frame is not None:
                resolution = [int(self.raw_frame.shape[1]), int(self.raw_frame.shape[0])]
            return {
                "id": self.camera_id,
                "name": self.name,
                "source": self.source,
                "active": True,
                "online": self._is_online(),
                "fps": self.fps,
                "inference_ms": self.inference_ms,
                "device": self.device,
                "detector_mode": self.detector_mode,
                "resolution": resolution,
                "detections": dict(self.detections),
                "frame_index": self.frame_index,
                "viewers": self.viewers,
                "last_frame_age_s": round(max(0.0, time.time() - self.last_frame_ts), 2) if self.last_frame_ts else None,
                "calibration": {
                    "ready": cal_ready,
                    "method": self.calibrator.method if self.calibrator else None,
                    "reproj_error_cm": round(self.calibrator.reproj_error_cm, 2) if self.calibrator else None,
                },
                "started_at": self.started_at,
            }

    def _is_online(self) -> bool:
        if self.source == "browser":
            return bool(self.ingest_connected and time.time() - self.last_ingest_ts < 12.0)
        return bool(self.last_frame_ts and time.time() - self.last_frame_ts < 5.0)


class FieldManager:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.registry = CameraRegistry(self.data_dir)
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()
        self.active_id: Optional[str] = None
        self.runtime: Optional[FieldCameraRuntime] = None
        self._heartbeats: Dict[str, float] = {}
        self._ingest_connected: Dict[str, bool] = {}

    # ------------------------------------------------------------------ cameras
    def list_cameras(self) -> List[Dict[str, object]]:
        cameras = self.registry.list()
        result: List[Dict[str, object]] = []
        for camera in cameras:
            camera = dict(camera)
            camera["phone_path"] = f"/camera/{camera['token']}"
            if self.active_id == camera["id"] and self.runtime is not None:
                camera.update(self.runtime.stats())
            else:
                camera.update(
                    {
                        "active": False,
                        "online": self._inactive_online(str(camera["id"])),
                        "fps": 0.0,
                        "inference_ms": 0.0,
                        "device": os.getenv("CLEAR_DEVICE", "auto"),
                        "resolution": None,
                        "detections": {"person": 0, "racket": 0, "ball": 0},
                        "viewers": 0,
                        "calibration": self._calibration_stats(str(camera["id"])),
                    }
                )
            result.append(camera)
        return result

    def get_camera(self, camera_id: str) -> Optional[Dict[str, object]]:
        camera = self.registry.get(camera_id)
        if camera is None:
            return None
        camera = dict(camera)
        camera["phone_path"] = f"/camera/{camera['token']}"
        if self.active_id == camera_id and self.runtime is not None:
            camera.update(self.runtime.stats())
        else:
            camera.update(
                {
                    "active": False,
                    "online": self._inactive_online(camera_id),
                    "fps": 0.0,
                    "inference_ms": 0.0,
                    "resolution": None,
                    "detections": {"person": 0, "racket": 0, "ball": 0},
                    "calibration": self._calibration_stats(camera_id),
                }
            )
        return camera

    def get_camera_by_token(self, token: str) -> Optional[Dict[str, object]]:
        if not token:
            return None
        for camera in self.registry.list():
            if camera.get("token") == token:
                return self.get_camera(str(camera["id"]))
        return None

    def get_calibration(self, camera_id: str) -> Optional[Dict[str, object]]:
        path = self.registry.calibration_path(camera_id)
        if not path.exists():
            return None
        try:
            cal = CourtCalibrator.load(path)
        except Exception:
            return None
        return {
            "method": cal.method,
            "anchors_px": {k: list(v) for k, v in cal.anchors_px.items()},
            "reproj_error_px": round(cal.reproj_error_px, 2),
            "reproj_error_cm": round(cal.reproj_error_cm, 2),
        }

    def _calibration_stats(self, camera_id: str) -> Dict[str, object]:
        path = self.registry.calibration_path(camera_id)
        if not path.exists():
            return {"ready": False, "method": None, "reproj_error_cm": None}
        try:
            cal = CourtCalibrator.load(path)
            return {
                "ready": cal.H_court_to_img is not None,
                "method": cal.method,
                "reproj_error_cm": round(cal.reproj_error_cm, 2),
            }
        except Exception:
            return {"ready": False, "method": None, "reproj_error_cm": None}

    def create_camera(self, name: str, source: str, rtsp_url: str = "") -> Dict[str, object]:
        return self.registry.create(name, source, rtsp_url)

    def update_camera(self, camera_id: str, **changes: object) -> Optional[Dict[str, object]]:
        updated = self.registry.update(camera_id, **changes)
        if updated is None:
            return None
        if self.active_id == camera_id and self.runtime is not None:
            with self.runtime.lock:
                self.runtime.camera.update(updated)
                if "court_mode" in changes or "overlays" in changes:
                    self.runtime.camera["court_mode"] = updated["court_mode"]
                    self.runtime.camera["overlays"] = updated["overlays"]
                if "detector" in changes and self.runtime.detector is not None:
                    det_cfg = updated.get("detector", {})
                    if isinstance(det_cfg, dict):
                        self.runtime.detector.player_conf_thresh = float(det_cfg.get("person", 0.35))
                        self.runtime.detector.racket_conf_thresh = float(det_cfg.get("racket", 0.25))
                        self.runtime.detector.ball_conf_thresh = float(det_cfg.get("ball", 0.18))
        return self.get_camera(camera_id)

    def delete_camera(self, camera_id: str) -> bool:
        if self.active_id == camera_id:
            self.deactivate()
        return self.registry.delete(camera_id)

    # ------------------------------------------------------------------ active channel
    def activate(self, camera_id: str) -> Optional[Dict[str, object]]:
        camera = self.registry.get(camera_id)
        if camera is None:
            return None
        with self._switch_lock:
            if self.active_id == camera_id and self.runtime is not None:
                return self.get_camera(camera_id)
            self._stop_runtime()
            runtime = FieldCameraRuntime(camera, self.data_dir)
            with self._lock:
                self.active_id = camera_id
                self.runtime = runtime
            runtime.start()
            return self.get_camera(camera_id)

    def _stop_runtime(self) -> None:
        old: Optional[FieldCameraRuntime]
        with self._lock:
            old = self.runtime
            self.runtime = None
            self.active_id = None
        if old is not None:
            old.stop()

    def deactivate(self) -> None:
        with self._switch_lock:
            self._stop_runtime()

    def shutdown(self) -> None:
        with self._switch_lock:
            self._stop_runtime()

    # ------------------------------------------------------------------ ingest
    def heartbeat(self, camera_id: str) -> None:
        self._heartbeats[camera_id] = time.time()
        self._ingest_connected[camera_id] = True
        if self.active_id == camera_id and self.runtime is not None:
            self.runtime.heartbeat()

    def set_ingest_connected(self, camera_id: str, connected: bool) -> None:
        self._ingest_connected[camera_id] = bool(connected)
        if connected:
            self._heartbeats[camera_id] = time.time()
        if self.active_id == camera_id and self.runtime is not None:
            self.runtime.set_ingest_connected(connected)

    def submit_jpeg(self, camera_id: str, payload: bytes) -> bool:
        if self.active_id != camera_id or self.runtime is None:
            return False
        self._heartbeats[camera_id] = time.time()
        self._ingest_connected[camera_id] = True
        return self.runtime.submit_jpeg(payload)

    def _inactive_online(self, camera_id: str) -> bool:
        if self._ingest_connected.get(camera_id):
            return time.time() - self._heartbeats.get(camera_id, 0.0) < 12.0
        return False

    # ------------------------------------------------------------------ calibration
    def save_calibration(
        self,
        camera_id: str,
        anchors_px: Dict[str, List[float]],
        method: str = "manual",
    ) -> Optional[CourtCalibrator]:
        camera = self.registry.get(camera_id)
        if camera is None:
            return None
        clean = {
            name: (float(point[0]), float(point[1]))
            for name, point in anchors_px.items()
            if isinstance(point, (list, tuple)) and len(point) == 2
        }
        if len(clean) < 4:
            raise ValueError("At least 4 valid court anchors are required.")
        cal = CourtCalibrator(anchors_px=clean)
        cal.method = method
        path = self.registry.calibration_path(camera_id)
        cal.save(path)
        self.registry.update(camera_id, calib_method=method)
        if self.active_id == camera_id and self.runtime is not None:
            self.runtime.set_calibrator(cal)
        return cal

    def auto_calibrate(self, camera_id: str) -> Dict[str, object]:
        runtime = self._require_active_runtime(camera_id)
        frame = self._raw_frame(runtime)
        if frame is None:
            raise ValueError("No frame available. Activate the camera and wait for video.")
        quad, confidence, note = detect_court_quad(frame)
        if quad is None:
            raise ValueError(note)
        cal = self.save_calibration(camera_id, anchors_from_quad(quad), method="auto")
        return {
            "ok": True,
            "method": "auto",
            "confidence": confidence,
            "note": note,
            "anchors_px": anchors_from_quad(quad),
            "reproj_error_cm": round(cal.reproj_error_cm, 2) if cal else None,
        }

    def segment_calibrate(self, camera_id: str) -> Dict[str, object]:
        runtime = self._require_active_runtime(camera_id)
        weights = os.getenv("CLEAR_COURT_SEG_WEIGHTS", "")
        if not weights:
            raise ValueError("Court segmentation is not configured. Set CLEAR_COURT_SEG_WEIGHTS.")
        frame = self._raw_frame(runtime)
        if frame is None:
            raise ValueError("No frame available. Activate the camera and wait for video.")
        quad, confidence, note = detect_court_with_segmentation(frame, weights)
        if quad is None:
            raise ValueError(note)
        cal = self.save_calibration(camera_id, anchors_from_quad(quad), method="segmentation")
        return {
            "ok": True,
            "method": "segmentation",
            "confidence": confidence,
            "note": note,
            "anchors_px": anchors_from_quad(quad),
            "reproj_error_cm": round(cal.reproj_error_cm, 2) if cal else None,
        }

    def _require_active_runtime(self, camera_id: str) -> FieldCameraRuntime:
        if self.active_id != camera_id or self.runtime is None:
            raise ValueError("Camera is not active.")
        return self.runtime

    def _raw_frame(self, runtime: FieldCameraRuntime) -> Optional[np.ndarray]:
        with runtime.lock:
            return None if runtime.raw_frame is None else runtime.raw_frame.copy()

    # ------------------------------------------------------------------ snapshots
    def snapshot_jpeg(self, camera_id: str, raw: bool = False) -> Optional[bytes]:
        if self.active_id == camera_id and self.runtime is not None:
            return self.runtime.snapshot_jpeg(raw=raw)
        return None

    def save_snapshot(self, camera_id: str, raw: bool = False) -> Optional[Path]:
        jpeg = self.snapshot_jpeg(camera_id, raw=raw)
        if jpeg is None:
            return None
        session_dir = self.registry.session_dir(camera_id)
        shots = session_dir / "snapshots"
        shots.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = shots / f"{stamp}{'_raw' if raw else ''}.jpg"
        path.write_bytes(jpeg)
        runtime = self.runtime
        detections = dict(runtime.detections) if runtime is not None else {}
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "camera_id": camera_id,
            "event": "snapshot",
            "raw": raw,
            "path": str(path),
            "detections": detections,
        }
        with (session_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
        return path

    # ------------------------------------------------------------------ stats
    def viewer_count(self, camera_id: str, delta: int) -> int:
        if self.active_id == camera_id and self.runtime is not None:
            with self.runtime.lock:
                self.runtime.viewers = max(0, self.runtime.viewers + delta)
                return self.runtime.viewers
        return 0

    def active_stats(self) -> Optional[Dict[str, object]]:
        if self.active_id is None:
            return None
        return self.get_camera(self.active_id)


def _resize_max_width(frame: np.ndarray, max_width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    return cv2.resize(frame, (max_width, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)


def _draw_box(
    frame: np.ndarray,
    bbox: Tuple[float, float, float, float],
    color: Tuple[int, int, int],
    label: str,
    thickness: int = 2,
) -> None:
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
    ty = max(th + 6, y1 - 6)
    cv2.rectangle(frame, (x1, ty - th - 5), (x1 + tw + 8, ty + 4), (18, 22, 28), -1)
    cv2.putText(frame, label, (x1 + 4, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 1, cv2.LINE_AA)
