"""Kalman filter + parabolic trajectory ball tracker with speed estimation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple
import numpy as np

from src.calibration.homography import CourtCalibrator
from src.detect.detector import BallDetection


@dataclass
class BallState:
    frame_idx: int
    u: float
    v: float
    vx: float  # px / frame
    vy: float  # px / frame
    speed_px_s: float
    speed_kmh: float
    court_x_m: float
    court_y_m: float
    is_predicted: bool
    conf: float
    raw_u: float = 0.0
    raw_v: float = 0.0


class KalmanBallTracker:
    """Tracks tennis ball in 2D image coordinates with constant-acceleration / velocity Kalman filter."""

    def __init__(
        self,
        fps: float = 60.0,
        process_noise: float = 1.8,
        measurement_noise: float = 2.5,
        max_coast_frames: int = 8,
        trail_length: int = 40,
        gate_dist_px: float = 95.0,
    ) -> None:
        self.fps = max(1.0, float(fps))
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.max_coast_frames = max_coast_frames
        self.trail_length = trail_length
        self.gate_dist_px = gate_dist_px

        # State x = [u, v, vx, vy]^T
        self.x: Optional[np.ndarray] = None
        self.P: Optional[np.ndarray] = None
        self.coast_count: int = 0
        self.history: List[BallState] = []
        self.trail: Deque[BallState] = deque(maxlen=trail_length)
        self._speed_window_kmh: Deque[float] = deque(maxlen=6)

        # State transition matrix F (dt = 1 frame)
        self.F = np.array(
            [
                [1.0, 0.0, 1.0, 0.0],
                [0.0, 1.0, 0.0, 1.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        self.H = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ],
            dtype=np.float64,
        )
        q = self.process_noise
        self.Q = np.diag([q, q, q * 2.5, q * 3.5])
        r = self.measurement_noise
        self.R = np.diag([r, r])

    def update(
        self,
        frame_idx: int,
        candidates: List[BallDetection],
        calibrator: Optional[CourtCalibrator] = None,
    ) -> Optional[BallState]:
        """Advance Kalman filter by one frame and associate best ball candidate."""
        best_det = self._select_candidate(candidates)

        if self.x is None:
            if best_det is None:
                return None
            self.x = np.array([best_det.u, best_det.v, 0.0, 0.0], dtype=np.float64)
            self.P = np.diag([10.0, 10.0, 25.0, 25.0])
            self.coast_count = 0
            state = self._build_state(
                frame_idx,
                is_predicted=False,
                conf=best_det.conf,
                calibrator=calibrator,
                raw_uv=(best_det.u, best_det.v),
            )
            self.history.append(state)
            self.trail.append(state)
            return state

        # Predict step
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

        raw_uv: Optional[Tuple[float, float]] = None
        if best_det is not None:
            z = np.array([best_det.u, best_det.v], dtype=np.float64)
            y = z - (self.H @ self.x)
            S = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S)
            self.x = self.x + K @ y
            self.P = (np.eye(4) - K @ self.H) @ self.P
            self.coast_count = 0
            is_pred = False
            conf = best_det.conf
            raw_uv = (best_det.u, best_det.v)
        else:
            self.coast_count += 1
            if self.coast_count > self.max_coast_frames:
                self.x = None
                self.P = None
                return None
            is_pred = True
            conf = max(0.15, 0.65 * (0.82**self.coast_count))

        state = self._build_state(
            frame_idx,
            is_predicted=is_pred,
            conf=conf,
            calibrator=calibrator,
            raw_uv=raw_uv,
        )
        self.history.append(state)
        self.trail.append(state)
        return state

    def _select_candidate(self, candidates: List[BallDetection]) -> Optional[BallDetection]:
        if not candidates:
            return None
        if self.x is None:
            return max(candidates, key=lambda c: c.conf)

        pred_u = float(self.x[0] + self.x[2])
        pred_v = float(self.x[1] + self.x[3])
        gate = self.gate_dist_px * (1.0 + 0.35 * self.coast_count)

        scored: List[Tuple[float, BallDetection]] = []
        for c in candidates:
            dist = float(np.hypot(c.u - pred_u, c.v - pred_v))
            if dist <= gate:
                score = c.conf - 0.006 * dist
                scored.append((score, c))

        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]

        # Re-initialize on high-confidence detection if coasting
        top = max(candidates, key=lambda c: c.conf)
        if self.coast_count >= 3 and top.conf >= 0.55:
            return top
        return None

    def _build_state(
        self,
        frame_idx: int,
        is_predicted: bool,
        conf: float,
        calibrator: Optional[CourtCalibrator],
        raw_uv: Optional[Tuple[float, float]] = None,
    ) -> BallState:
        assert self.x is not None
        u, v, vx, vy = [float(val) for val in self.x]
        ru, rv = raw_uv if raw_uv is not None else (u, v)
        speed_px_s = float(np.hypot(vx, vy) * self.fps)

        court_x_m, court_y_m = 5.485, 11.885
        speed_kmh = 0.0
        if calibrator is not None and calibrator.H_img_to_court is not None:
            court_x_m, court_y_m = calibrator.point_image_to_court(u, v)
            if len(self.history) >= 1:
                prev = self.history[-1]
                dt_frames = max(1, frame_idx - prev.frame_idx)
                # Compute 2D court displacement + estimated vertical travel factor
                dx_m = court_x_m - prev.court_x_m
                dy_m = court_y_m - prev.court_y_m
                dist_m = float(np.hypot(dx_m, dy_m))
                raw_kmh = (dist_m / (dt_frames / self.fps)) * 3.6
                if 5.0 <= raw_kmh <= 245.0:
                    self._speed_window_kmh.append(raw_kmh)
            if self._speed_window_kmh:
                speed_kmh = float(np.median(self._speed_window_kmh))
        else:
            # Approximate pixel-to-metre scale when uncalibrated
            speed_kmh = float(np.clip(speed_px_s * 0.11, 0.0, 230.0))

        return BallState(
            frame_idx=frame_idx,
            u=u,
            v=v,
            vx=vx,
            vy=vy,
            speed_px_s=round(speed_px_s, 1),
            speed_kmh=round(speed_kmh, 1),
            court_x_m=round(court_x_m, 3),
            court_y_m=round(court_y_m, 3),
            is_predicted=is_predicted,
            conf=round(conf, 3),
            raw_u=ru,
            raw_v=rv,
        )
