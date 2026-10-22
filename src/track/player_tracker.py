"""ByteTrack-inspired two-player tracker with court-plane foot projection and distance stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple
import numpy as np

from src.calibration.homography import CourtCalibrator
from src.detect.detector import PlayerDetection


@dataclass
class PlayerState:
    player_id: int  # 1 = Near Player, 2 = Far Player
    label: str
    court_half: Literal["near", "far"]
    bbox: Tuple[float, float, float, float]
    foot_uv: Tuple[float, float]
    court_xy_m: Tuple[float, float]
    speed_kmh: float = 0.0
    max_speed_kmh: float = 0.0
    distance_m: float = 0.0
    conf: float = 0.9
    coast_frames: int = 0
    court_history_m: List[Tuple[float, float]] = field(default_factory=list)


class PlayerTracker:
    """Maintains persistent tracks for Player 1 (Near) and Player 2 (Far) across a rally."""

    def __init__(
        self,
        fps: float = 60.0,
        smoothing_alpha: float = 0.45,
        max_coast_frames: int = 20,
    ) -> None:
        self.fps = max(1.0, float(fps))
        self.smoothing_alpha = smoothing_alpha
        self.max_coast_frames = max_coast_frames
        self.tracks: Dict[int, PlayerState] = {}

    def update(
        self,
        frame_idx: int,
        detections: List[PlayerDetection],
        calibrator: Optional[CourtCalibrator] = None,
    ) -> Dict[int, PlayerState]:
        near_dets = [d for d in detections if d.court_half == "near"]
        far_dets = [d for d in detections if d.court_half == "far"]

        self._update_slot(
            player_id=1,
            label="P1 (NEAR)",
            court_half="near",
            candidates=near_dets,
            calibrator=calibrator,
        )
        self._update_slot(
            player_id=2,
            label="P2 (FAR)",
            court_half="far",
            candidates=far_dets,
            calibrator=calibrator,
        )

        return {
            pid: st
            for pid, st in self.tracks.items()
            if st.coast_frames <= self.max_coast_frames
        }

    def _update_slot(
        self,
        player_id: int,
        label: str,
        court_half: Literal["near", "far"],
        candidates: List[PlayerDetection],
        calibrator: Optional[CourtCalibrator],
    ) -> None:
        existing = self.tracks.get(player_id)
        best_det: Optional[PlayerDetection] = None

        if candidates:
            if existing is None:
                best_det = max(candidates, key=lambda d: d.conf)
            else:
                # ByteTrack-style association: prioritize close foot-point + high confidence
                ex_u, ex_v = existing.foot_uv
                best_det = min(
                    candidates,
                    key=lambda d: np.hypot(d.foot_uv[0] - ex_u, d.foot_uv[1] - ex_v) - 35.0 * d.conf,
                )

        if best_det is None:
            if existing is not None:
                existing.coast_frames += 1
                existing.speed_kmh = round(existing.speed_kmh * 0.85, 1)
            return

        if existing is None:
            cx_m, cy_m = self._project_foot(best_det.foot_uv, court_half, calibrator)
            state = PlayerState(
                player_id=player_id,
                label=label,
                court_half=court_half,
                bbox=best_det.bbox,
                foot_uv=best_det.foot_uv,
                court_xy_m=(cx_m, cy_m),
                conf=best_det.conf,
                coast_frames=0,
                court_history_m=[(cx_m, cy_m)],
            )
            self.tracks[player_id] = state
            return

        # Smooth bounding box & foot point
        a = self.smoothing_alpha
        old_b = existing.bbox
        new_b = best_det.bbox
        sm_bbox = (
            (1 - a) * old_b[0] + a * new_b[0],
            (1 - a) * old_b[1] + a * new_b[1],
            (1 - a) * old_b[2] + a * new_b[2],
            (1 - a) * old_b[3] + a * new_b[3],
        )
        sm_foot = (0.5 * (sm_bbox[0] + sm_bbox[2]), sm_bbox[3])

        cx_m, cy_m = self._project_foot(sm_foot, court_half, calibrator)
        prev_x, prev_y = existing.court_xy_m
        step_m = float(np.hypot(cx_m - prev_x, cy_m - prev_y))

        dt_s = max(1, existing.coast_frames + 1) / self.fps
        inst_kmh = (step_m / dt_s) * 3.6
        if step_m < 1.2:  # Ignore teleports/glitches
            existing.distance_m = round(existing.distance_m + step_m, 2)
            existing.speed_kmh = round(0.65 * existing.speed_kmh + 0.35 * min(34.0, inst_kmh), 1)
            existing.max_speed_kmh = round(max(existing.max_speed_kmh, existing.speed_kmh), 1)

        existing.bbox = sm_bbox
        existing.foot_uv = sm_foot
        existing.court_xy_m = (cx_m, cy_m)
        existing.conf = best_det.conf
        existing.coast_frames = 0
        existing.court_history_m.append((cx_m, cy_m))

    @staticmethod
    def _project_foot(
        foot_uv: Tuple[float, float],
        court_half: Literal["near", "far"],
        calibrator: Optional[CourtCalibrator],
    ) -> Tuple[float, float]:
        if calibrator is not None and calibrator.H_img_to_court is not None:
            x_m, y_m = calibrator.point_image_to_court(foot_uv[0], foot_uv[1])
            x_m = float(np.clip(x_m, -2.0, 12.97))
            y_m = float(np.clip(y_m, -3.5, 27.5))
            return round(x_m, 3), round(y_m, 3)
        return (5.485, 22.0 if court_half == "near" else 1.8)

    def get_summary_stats(self) -> Dict[str, Dict[str, object]]:
        summary: Dict[str, Dict[str, object]] = {}
        for pid, st in self.tracks.items():
            pts = np.array(st.court_history_m, dtype=np.float64) if st.court_history_m else np.zeros((1, 2))
            # Zone breakdown: Baseline vs Transition (No-Man's-Land) vs Net
            if st.court_half == "near":
                baseline_pct = float(np.mean(pts[:, 1] >= 21.5) * 100.0)
                net_pct = float(np.mean(pts[:, 1] <= 16.5) * 100.0)
            else:
                baseline_pct = float(np.mean(pts[:, 1] <= 2.3) * 100.0)
                net_pct = float(np.mean(pts[:, 1] >= 7.3) * 100.0)
            trans_pct = max(0.0, 100.0 - baseline_pct - net_pct)

            summary[st.label] = {
                "player_id": pid,
                "court_half": st.court_half,
                "distance_m": round(st.distance_m, 2),
                "max_speed_kmh": round(st.max_speed_kmh, 1),
                "zone_baseline_pct": round(baseline_pct, 1),
                "zone_transition_pct": round(trans_pct, 1),
                "zone_net_pct": round(net_pct, 1),
                "samples": len(st.court_history_m),
            }
        return summary
