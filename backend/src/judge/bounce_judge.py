"""Bounce and stroke detection via trajectory vertex fitting + homography line calling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Literal, Optional
import numpy as np

from src.calibration.court_geometry import CourtMode, SPEC, evaluate_court_point
from src.calibration.homography import CourtCalibrator
from src.track.ball_tracker import BallState
from src.track.player_tracker import PlayerState


@dataclass
class BounceEvent:
    frame_idx: int
    u: float
    v: float
    x_m: float
    y_m: float
    call: Literal["IN", "OUT"]
    is_in: bool
    signed_margin_cm: float
    abs_margin_cm: float
    closest_line: str
    in_doubt_zone: bool
    confidence: float
    speed_kmh: float
    court_half: Literal["near", "far"]
    detector_mode: str = "parabolic_fit"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class StrokeEvent:
    frame_idx: int
    player_id: int
    u: float
    v: float
    x_m: float
    y_m: float
    shot_speed_kmh: float


class BounceJudge:
    """Detects ball bounces and racket strokes from ball trajectory and calls IN/OUT."""

    def __init__(
        self,
        court_mode: CourtMode = "singles",
        ball_contact_radius_cm: float = 3.8,
        doubt_zone_cm: float = 15.0,
        min_bounce_vy_px: float = 1.6,
        min_frames_between_bounces: int = 12,
        use_parabolic_refinement: bool = True,
    ) -> None:
        self.court_mode = court_mode
        self.ball_contact_radius_cm = ball_contact_radius_cm
        self.doubt_zone_cm = doubt_zone_cm
        self.min_bounce_vy_px = min_bounce_vy_px
        self.min_frames_between_bounces = min_frames_between_bounces
        self.use_parabolic_refinement = use_parabolic_refinement

        self.bounces: List[BounceEvent] = []
        self.strokes: List[StrokeEvent] = []
        self._last_bounce_frame: int = -999
        self._last_stroke_frame: int = -999

    def update(
        self,
        ball_history: List[BallState],
        players: Dict[int, PlayerState],
        calibrator: CourtCalibrator,
    ) -> Optional[BounceEvent]:
        """Inspect recent ball trajectory window (7 frames) for a bounce or player hit."""
        if len(ball_history) < 7:
            return None

        window = ball_history[-7:]
        center = window[3]  # Candidate vertex at index 3 (t-3) for symmetric check

        if center.frame_idx - self._last_bounce_frame < self.min_frames_between_bounces:
            return None

        # Use raw_u/raw_v when available for sharp cusp localization, fallback to Kalman u/v
        v_vals = np.array([s.raw_v if not s.is_predicted else s.v for s in window], dtype=np.float64)
        u_vals = np.array([s.raw_u if not s.is_predicted else s.u for s in window], dtype=np.float64)
        y_m_vals = np.array([s.court_y_m for s in window], dtype=np.float64)

        # Compute vertical bounce impulse: difference between incoming and outgoing vertical slope.
        # Perspective slope cancels out, leaving pure vertical rebound cusp for both Near and Far courts.
        imp_prev = v_vals[2] - 0.5 * (v_vals[0] + v_vals[4])
        imp_curr = v_vals[3] - 0.5 * (v_vals[1] + v_vals[5])
        imp_next = v_vals[4] - 0.5 * (v_vals[2] + v_vals[6])

        du_before = u_vals[3] - u_vals[0]
        du_after = u_vals[6] - u_vals[3]
        dy_before = y_m_vals[3] - y_m_vals[0]
        dy_after = y_m_vals[6] - y_m_vals[3]

        near_player_id = self._check_player_proximity(center, players)

        # 1. Racket Stroke / Hit detection (ball near player & reverses North-South court direction)
        if near_player_id is not None and (dy_before * dy_after < -0.05):
            if center.frame_idx - self._last_stroke_frame >= 20:
                self._last_stroke_frame = center.frame_idx
                self.strokes.append(
                    StrokeEvent(
                        frame_idx=center.frame_idx,
                        player_id=near_player_id,
                        u=round(center.u, 1),
                        v=round(center.v, 1),
                        x_m=center.court_x_m,
                        y_m=center.court_y_m,
                        shot_speed_kmh=max(center.speed_kmh, window[-1].speed_kmh),
                    )
                )
            return None

        # 2. Ground bounce detection:
        # Sharp positive vertical impulse peak (ball hits clay and rebounds upward)
        is_impulse_peak = (
            (imp_curr >= imp_prev)
            and (imp_curr >= imp_next)
            and (imp_curr >= self.min_bounce_vy_px)
        )

        if is_impulse_peak and (center.frame_idx - self._last_stroke_frame >= 12):
            if self.use_parabolic_refinement:
                # Sub-pixel cusp intersection from incoming and outgoing rays around raw vertex
                t_in = np.array([-3.0, -2.0, -1.0, 0.0], dtype=np.float64)
                t_out = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float64)
                v_in_0 = float(np.polyval(np.polyfit(t_in, v_vals[:4], deg=1), 0.0))
                v_out_0 = float(np.polyval(np.polyfit(t_out, v_vals[3:], deg=1), 0.0))
                u_in_0 = float(np.polyval(np.polyfit(t_in, u_vals[:4], deg=1), 0.0))
                u_out_0 = float(np.polyval(np.polyfit(t_out, u_vals[3:], deg=1), 0.0))

                bounce_u = 0.70 * float(u_vals[3]) + 0.15 * u_in_0 + 0.15 * u_out_0
                bounce_v = max(float(v_vals[3]), 0.60 * float(v_vals[3]) + 0.20 * v_in_0 + 0.20 * v_out_0)
                mode_tag = "parabolic_fit"
            else:
                # Baseline B3: unrefined Kalman state at vertex
                bounce_u = float(center.u)
                bounce_v = float(center.v)
                mode_tag = "vy_sign_b3"

            x_m, y_m = calibrator.point_image_to_court(bounce_u, bounce_v)
            court_half: Literal["near", "far"] = "far" if y_m < SPEC.net_y_m else "near"

            eval_res = evaluate_court_point(
                x_m=x_m,
                y_m=y_m,
                mode=self.court_mode,
                target_half=court_half,
                ball_contact_radius_cm=self.ball_contact_radius_cm,
                doubt_zone_cm=self.doubt_zone_cm,
                reproj_uncertainty_cm=calibrator.reproj_error_cm,
            )

            event = BounceEvent(
                frame_idx=center.frame_idx,
                u=round(bounce_u, 2),
                v=round(bounce_v, 2),
                x_m=float(eval_res["x_m"]),
                y_m=float(eval_res["y_m"]),
                call=eval_res["call"],  # type: ignore[arg-type]
                is_in=bool(eval_res["is_in"]),
                signed_margin_cm=float(eval_res["signed_margin_cm"]),
                abs_margin_cm=float(eval_res["abs_margin_cm"]),
                closest_line=str(eval_res["closest_line"]),
                in_doubt_zone=bool(eval_res["in_doubt_zone"]),
                confidence=float(eval_res["confidence"]),
                speed_kmh=round(max(center.speed_kmh, window[1].speed_kmh), 1),
                court_half=court_half,
                detector_mode=mode_tag,
            )
            self._last_bounce_frame = center.frame_idx
            self.bounces.append(event)
            return event

        # 2. Racket Stroke / Hit detection (reversal of direction between players)
        near_player_id = self._check_player_proximity(center, players)
        if (
            (center.frame_idx - self._last_stroke_frame >= 24)
            and (center.frame_idx - self._last_bounce_frame >= 10)
            and ((du_before * du_after < -1.0) or (dy_before * dy_after < -0.2))
        ):
            self._last_stroke_frame = center.frame_idx
            hitter_id = near_player_id or (1 if center.court_y_m > SPEC.net_y_m else 2)
            self.strokes.append(
                StrokeEvent(
                    frame_idx=center.frame_idx,
                    player_id=hitter_id,
                    u=round(center.u, 1),
                    v=round(center.v, 1),
                    x_m=center.court_x_m,
                    y_m=center.court_y_m,
                    shot_speed_kmh=max(center.speed_kmh, window[-1].speed_kmh),
                )
            )

        return None

    @staticmethod
    def _check_player_proximity(
        ball: BallState,
        players: Dict[int, PlayerState],
    ) -> Optional[int]:
        for pid, p in players.items():
            x1, y1, x2, y2 = p.bbox
            pad_x = max(22.0, (x2 - x1) * 0.45)
            pad_y = max(18.0, (y2 - y1) * 0.25)
            if (x1 - pad_x <= ball.u <= x2 + pad_x) and (y1 - pad_y <= ball.v <= y2 + pad_y * 0.5):
                return pid
        return None
