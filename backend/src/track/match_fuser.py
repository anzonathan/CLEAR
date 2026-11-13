"""Fuse two opposite-end field cameras into one shared court-coordinate track.

Each camera sees one half of the court up close (high pixel density for the
ball). Detections are projected through each camera's own homography into the
shared ITF court plane, then fed to a single court-space ball Kalman filter and
a single two-player tracker. Near/Far classification is already shared-court:
``y_m > net`` = P1 (near), ``y_m < net`` = P2 (far), independent of which camera
produced the detection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from src.calibration.homography import CourtCalibrator
from src.detect.detector import BallDetection, FrameDetections, PlayerDetection
from src.track.player_tracker import PlayerState, PlayerTracker


S = 100.0  # synthetic pixels per metre (unit-agnostic projection for PlayerTracker)


@dataclass
class FusedCameraInput:
    camera_id: str
    dets: FrameDetections
    calibrator: Optional[CourtCalibrator]


@dataclass
class FusedBallState:
    frame_idx: int
    x_m: float
    y_m: float
    vx_ms: float
    vy_ms: float
    speed_kmh: float
    conf: float
    is_predicted: bool
    source_camera: str = ""


@dataclass
class FusedTrack:
    ball: Optional[FusedBallState] = None
    players: Dict[int, PlayerState] = field(default_factory=dict)
    ball_trail: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=40))


class CourtBallTracker:
    """Constant-velocity Kalman filter tracking the ball in court metres (x, y)."""

    def __init__(
        self,
        fps: float = 15.0,
        gate_m: float = 2.5,
        max_coast: int = 8,
        measurement_noise_m: float = 0.06,
        process_noise_m2: float = 0.6,
        trail_length: int = 40,
    ) -> None:
        self.fps = max(1.0, float(fps))
        self.dt = 1.0 / self.fps
        self.gate_m = gate_m
        self.max_coast = max_coast
        self.trail_length = trail_length

        # State x = [x, y, vx, vy]^T in metres / metres-per-second
        self.x: Optional[np.ndarray] = None
        self.P: Optional[np.ndarray] = None
        self.F = np.array(
            [
                [1.0, 0.0, self.dt, 0.0],
                [0.0, 1.0, 0.0, self.dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        self.H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
        q = process_noise_m2
        self.Q = np.diag([q, q, q * 2.0, q * 2.0])
        r = measurement_noise_m
        self.R = np.diag([r, r])

        self.coast_count = 0
        self.history: List[FusedBallState] = []
        self.trail: Deque[Tuple[float, float]] = deque(maxlen=trail_length)

    def update(self, frame_idx: int, candidates: List[Tuple[float, float, float, str]]) -> Optional[FusedBallState]:
        """Advance by one frame. candidates = (x_m, y_m, conf, source_camera)."""
        best = self._select_candidate(candidates)

        if self.x is None:
            if best is None:
                return None
            x_m, y_m, conf, src = best
            self.x = np.array([x_m, y_m, 0.0, 0.0], dtype=np.float64)
            self.P = np.diag([0.5, 0.5, 4.0, 4.0])
            self.coast_count = 0
            state = self._build_state(frame_idx, conf, False, src)
            self.history.append(state)
            self.trail.append((state.x_m, state.y_m))
            return state

        # Predict
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

        if best is not None:
            x_m, y_m, conf, src = best
            z = np.array([x_m, y_m], dtype=np.float64)
            y_innov = z - (self.H @ self.x)
            S_mat = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S_mat)
            self.x = self.x + K @ y_innov
            self.P = (np.eye(4) - K @ self.H) @ self.P
            self.coast_count = 0
            is_pred = False
        else:
            self.coast_count += 1
            if self.coast_count > self.max_coast:
                self.x = None
                self.P = None
                return None
            is_pred = True
            conf = max(0.10, 0.6 * (0.8**self.coast_count))
            src = ""

        state = self._build_state(frame_idx, conf, is_pred, src)
        self.history.append(state)
        self.trail.append((state.x_m, state.y_m))
        return state

    def _select_candidate(self, candidates: List[Tuple[float, float, float, str]]) -> Optional[Tuple[float, float, float, str]]:
        if not candidates:
            return None
        if self.x is None:
            return max(candidates, key=lambda c: c[2])

        pred_x = float(self.x[0] + self.x[2] * self.dt)
        pred_y = float(self.x[1] + self.x[3] * self.dt)
        gate = self.gate_m * (1.0 + 0.4 * self.coast_count)

        scored: List[Tuple[float, Tuple[float, float, float, str]]] = []
        for c in candidates:
            dist = float(np.hypot(c[0] - pred_x, c[1] - pred_y))
            if dist <= gate:
                scored.append((c[2] - 0.15 * dist, c))
        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]

        top = max(candidates, key=lambda c: c[2])
        if self.coast_count >= 3 and top[2] >= 0.55:
            return top
        return None

    def _build_state(self, frame_idx: int, conf: float, is_predicted: bool, src: str) -> FusedBallState:
        assert self.x is not None
        x_m, y_m, vx, vy = [float(v) for v in self.x]
        speed_kmh = float(np.hypot(vx, vy)) * 3.6
        return FusedBallState(
            frame_idx=frame_idx,
            x_m=round(x_m, 3),
            y_m=round(y_m, 3),
            vx_ms=round(vx, 3),
            vy_ms=round(vy, 3),
            speed_kmh=round(speed_kmh, 1),
            conf=round(conf, 3),
            is_predicted=is_predicted,
            source_camera=src,
        )


def synthetic_calibrator() -> CourtCalibrator:
    """Linear 100 px/m identity court<->pixel mapping for unit-agnostic tracking."""
    cal = CourtCalibrator()
    h = np.array([[S, 0.0, 0.0], [0.0, S, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    cal.H_court_to_img = h
    cal.H_img_to_court = np.linalg.inv(h)
    cal.method = "synthetic"
    return cal


def project_fused_to_image(fused: FusedTrack, cal: CourtCalibrator) -> Dict[str, object]:
    """Project fused court-space ball/players/trail into one camera's pixel space."""
    if cal is None or cal.H_court_to_img is None:
        return {}
    out: Dict[str, object] = {}
    if fused.ball is not None:
        u, v = cal.point_court_to_image(fused.ball.x_m, fused.ball.y_m)
        out["ball"] = (float(u), float(v), fused.ball.speed_kmh, fused.ball.is_predicted)
    out["players"] = [
        (int(pid), st.label, *cal.point_court_to_image(st.court_xy_m[0], st.court_xy_m[1]))
        for pid, st in fused.players.items()
    ]
    out["trail"] = [list(cal.point_court_to_image(x, y)) for x, y in fused.ball_trail]
    return out


class MatchFuser:
    """Shared court-space ball + two-player tracker fed by multiple cameras."""

    def __init__(self, fps: float = 15.0) -> None:
        self.fps = max(1.0, float(fps))
        self.ball_tracker = CourtBallTracker(fps=self.fps)
        self.player_tracker = PlayerTracker(fps=self.fps)
        self.synth_cal = synthetic_calibrator()
        self.frame_index = 0
        self.latest: FusedTrack = FusedTrack()

    def update(self, inputs: List[FusedCameraInput]) -> FusedTrack:
        self.frame_index += 1
        ball_candidates: List[Tuple[float, float, float, str]] = []
        player_detections: List[PlayerDetection] = []

        for cam in inputs:
            cal = cam.calibrator
            if cal is None or cal.H_img_to_court is None:
                continue
            for b in cam.dets.balls:
                x_m, y_m = cal.point_image_to_court(b.u, b.v)
                if not (-3.0 <= x_m <= 14.0 and -3.0 <= y_m <= 27.0):
                    continue
                # Prefer the camera where the ball is physically larger (closer).
                conf = float(min(0.98, b.conf * (1.0 + 0.02 * b.radius)))
                ball_candidates.append((x_m, y_m, conf, cam.camera_id))
            for p in cam.dets.players:
                x_m, y_m = cal.point_image_to_court(p.foot_uv[0], p.foot_uv[1])
                if not (-3.5 <= x_m <= 14.5 and -4.5 <= y_m <= 28.5):
                    continue
                player_detections.append(
                    PlayerDetection(
                        bbox=p.bbox,
                        conf=p.conf,
                        foot_uv=(x_m * S, y_m * S),
                        court_half=p.court_half,
                        source=p.source,
                    )
                )

        ball = self.ball_tracker.update(self.frame_index, ball_candidates)
        players = self.player_tracker.update(self.frame_index, player_detections, self.synth_cal)

        self.latest = FusedTrack(
            ball=ball,
            players=players,
            ball_trail=self.ball_tracker.trail,
        )
        return self.latest

    def snapshot(self) -> Dict[str, object]:
        ball = self.latest.ball
        players = self.latest.players
        return {
            "frame_index": self.frame_index,
            "ball": (
                {
                    "x_m": ball.x_m,
                    "y_m": ball.y_m,
                    "speed_kmh": ball.speed_kmh,
                    "conf": ball.conf,
                    "is_predicted": ball.is_predicted,
                    "source_camera": ball.source_camera,
                }
                if ball is not None
                else None
            ),
            "players": {
                str(pid): {
                    "label": st.label,
                    "court_half": st.court_half,
                    "x_m": st.court_xy_m[0],
                    "y_m": st.court_xy_m[1],
                    "speed_kmh": st.speed_kmh,
                    "conf": st.conf,
                }
                for pid, st in players.items()
            },
            "ball_trail": [list(pt) for pt in self.latest.ball_trail],
        }
