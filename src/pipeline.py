"""End-to-end CLEAR video processing pipeline (Detection -> Tracking -> Bounce Judge -> Score -> HUD)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.calibration.court_geometry import COURT_LINES_M, SPEC
from src.calibration.homography import CameraDriftMonitor, CourtCalibrator
from src.calibration.virtual_court import VirtualCourtRenderer
from src.detect.detector import HybridTennisDetector
from src.faults.fault_events import FaultEvent
from src.faults.foot_faults import FootFaultJudge
from src.judge.bounce_judge import BounceJudge
from src.judge.hud_renderer import BroadcastHUDRenderer
from src.score.score_engine import TennisScoreEngine
from src.track.ball_tracker import BallState, KalmanBallTracker
from src.track.player_tracker import PlayerTracker


class ClearPipeline:
    """Runs complete CLEAR pipeline on frames or video files."""

    def __init__(
        self,
        calibrator: Optional[CourtCalibrator] = None,
        court_mode: Literal["singles", "doubles"] = "singles",
        detector_mode: Literal["hybrid", "yolo", "classical"] = "hybrid",
        fps: float = 60.0,
        doubt_zone_cm: float = 15.0,
        use_3frame_temporal: bool = True,
        use_parabolic_refinement: bool = True,
    ) -> None:
        self.fps = max(1.0, float(fps))
        self.court_mode: Literal["singles", "doubles"] = court_mode
        self.doubt_zone_cm = doubt_zone_cm
        self.calibrator = calibrator or CourtCalibrator.from_default_camera_geometry()
        self.virtual_court = VirtualCourtRenderer(
            calibrator=self.calibrator,
            court_mode=court_mode,
            doubt_zone_cm=doubt_zone_cm,
        )
        self.detector = HybridTennisDetector(
            mode=detector_mode,
            use_3frame_temporal=use_3frame_temporal,
        )
        self.ball_tracker = KalmanBallTracker(fps=self.fps)
        self.player_tracker = PlayerTracker(fps=self.fps)
        self.bounce_judge = BounceJudge(
            court_mode=court_mode,
            doubt_zone_cm=doubt_zone_cm,
            use_parabolic_refinement=use_parabolic_refinement,
        )
        self.score_engine = TennisScoreEngine()
        self.drift_monitor = CameraDriftMonitor()
        self.hud = BroadcastHUDRenderer(
            calibrator=self.calibrator,
            virtual_court=self.virtual_court,
        )
        self.foot_fault_judge = FootFaultJudge(court_mode=court_mode)
        self.fault_events: List[FaultEvent] = []
        self._gt_by_frame: Dict[int, dict] = {}

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        frame_idx: int,
    ) -> Tuple[np.ndarray, Optional[BallState]]:
        """Process single video frame and return annotated BGR frame + current BallState."""
        drift_px, is_drifted = self.drift_monitor.update(frame_bgr)
        dets = self.detector.detect(frame_bgr, frame_idx=frame_idx, calibrator=self.calibrator)

        ball_state = self.ball_tracker.update(
            frame_idx=frame_idx,
            candidates=dets.balls,
            calibrator=self.calibrator,
        )
        players = self.player_tracker.update(
            frame_idx=frame_idx,
            detections=dets.players,
            calibrator=self.calibrator,
        )

        new_bounce = self.bounce_judge.update(
            ball_history=self.ball_tracker.history,
            players=players,
            calibrator=self.calibrator,
        )
        if new_bounce is not None:
            self.score_engine.register_bounce(
                is_in=new_bounce.is_in,
                court_half=new_bounce.court_half,
                frame_idx=new_bounce.frame_idx,
            )

        self._evaluate_foot_faults(frame_idx)

        annotated = self.hud.render(
            frame_bgr=frame_bgr,
            frame_idx=frame_idx,
            ball_state=ball_state,
            ball_trail=self.ball_tracker.trail,
            players=players,
            bounces=self.bounce_judge.bounces,
            strokes=self.bounce_judge.strokes,
            score_engine=self.score_engine,
            drift_px=drift_px,
            is_drifted=is_drifted,
        )
        return annotated, ball_state

    def _load_gt(self, video_path: Path) -> None:
        """Load synthetic GT if present (same stem + _gt.json, or data/demo default)."""
        self._gt_by_frame = {}
        candidates = [
            video_path.with_name(video_path.stem + "_gt.json"),
            Path("data/demo/ucu_clay_rally_gt.json"),
        ]
        for p in candidates:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._gt_by_frame = {
                    int(f["frame_idx"]): f for f in data.get("frames", [])
                }
                break

    def _evaluate_foot_faults(self, frame_idx: int) -> None:
        """Call FootFaultJudge when GT marks a pre-contact serve."""
        gt = self._gt_by_frame.get(frame_idx)
        if not gt:
            return
        if not gt.get("service_motion_active") or not gt.get("pre_contact"):
            return

        server_id = gt.get("server_id")
        if server_id is None:
            return

        if int(server_id) == 1:
            left = gt.get("p1_left_foot_xy_m")
            right = gt.get("p1_right_foot_xy_m")
        else:
            left = gt.get("p2_left_foot_xy_m")
            right = gt.get("p2_right_foot_xy_m")

        if not left or not right:
            return

        event = self.foot_fault_judge.evaluate(
            frame_idx=frame_idx,
            serving_end=gt["serving_end"],
            left_foot_xy_m=(float(left[0]), float(left[1])),
            right_foot_xy_m=(float(right[0]), float(right[1])),
            service_motion_active=True,
            pre_contact=True,
            service_side=gt.get("service_side"),
            player_id=int(server_id),
            observation_confidence=1.0,
        )
        self.fault_events.append(event)

    def run_video(
        self,
        video_path: str | Path,
        out_dir: str | Path,
        max_frames: Optional[int] = None,
    ) -> Dict[str, object]:
        """Run pipeline on a video file and write annotated video, JSON logs, and 2D court chart."""
        in_path = Path(video_path)
        if not in_path.exists():
            raise FileNotFoundError(f"Video file not found: {in_path}")

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        self._load_gt(in_path)
        self.fault_events = []

        cap = cv2.VideoCapture(str(in_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {in_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        self.fps = float(fps)
        self.ball_tracker.fps = self.fps
        self.player_tracker.fps = self.fps

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        video_out_file = out_path / "annotated_rally.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_out_file), fourcc, self.fps, (w, h))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if max_frames is not None and frame_idx >= max_frames:
                break

            annotated, _ = self.process_frame(frame, frame_idx=frame_idx)
            writer.write(annotated)
            frame_idx += 1

        cap.release()
        writer.release()

        report = self.build_report(total_frames=frame_idx, video_out_path=str(video_out_file))
        (out_path / "bounces.json").write_text(
            json.dumps([b.to_dict() for b in self.bounce_judge.bounces], indent=2),
            encoding="utf-8",
        )
        (out_path / "summary.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        self.save_court_chart(out_path / "court_analytics.png")
        return report

    def build_report(
        self,
        total_frames: int,
        video_out_path: Optional[str] = None,
    ) -> Dict[str, object]:
        bounces = [b.to_dict() for b in self.bounce_judge.bounces]
        in_count = sum(1 for b in self.bounce_judge.bounces if b.is_in)
        out_count = len(bounces) - in_count
        doubt_count = sum(1 for b in self.bounce_judge.bounces if b.in_doubt_zone)
        speeds = [s.speed_kmh for s in self.ball_tracker.history if s.speed_kmh > 5.0]
        fault_dicts = [e.to_dict() for e in self.fault_events]

        return {
            "total_frames": total_frames,
            "fps": round(self.fps, 2),
            "court_mode": self.court_mode,
            "calibration": {
                "method": self.calibrator.method,
                "reproj_error_px": round(self.calibrator.reproj_error_px, 2),
                "reproj_error_cm": round(self.calibrator.reproj_error_cm, 2),
                "anchors_px": {k: list(v) for k, v in self.calibrator.anchors_px.items()},
            },
            "ball_tracking": {
                "tracked_frames": len(self.ball_tracker.history),
                "coverage_pct": round(100.0 * len(self.ball_tracker.history) / max(1, total_frames), 1),
                "avg_speed_kmh": round(float(np.mean(speeds)), 1) if speeds else 0.0,
                "max_speed_kmh": round(float(np.max(speeds)), 1) if speeds else 0.0,
                "rally_strokes": len(self.bounce_judge.strokes),
            },
            "line_calling": {
                "total_bounces": len(bounces),
                "in_calls": in_count,
                "out_calls": out_count,
                "doubt_zone_calls": doubt_count,
                "bounces": bounces,
            },
            "fault_events": fault_dicts,
            "foot_faults": [
                e for e in fault_dicts if e.get("status") in ("fault", "no_fault")
            ],
            "players": self.player_tracker.get_summary_stats(),
            "score": self.score_engine.to_dict(),
            "annotated_video": video_out_path,
        }

    def save_court_chart(self, out_file: str | Path) -> None:
        """Render publication-quality 2D court analytics chart (bounces, trajectories, player heatmaps)."""
        fig, axes = plt.subplots(1, 2, figsize=(11, 7.5), facecolor="#11161d")

        for ax in axes:
            ax.set_facecolor("#2b4c7e")
            rect = plt.Rectangle(
                (0, 0),
                SPEC.doubles_width_m,
                SPEC.length_m,
                facecolor="#b55435",
                alpha=0.88,
                zorder=1,
            )
            ax.add_patch(rect)
            for name, p1, p2, cat in COURT_LINES_M:
                lw = 2.2 if cat == "net" else 1.4
                ls = "--" if cat == "net" else "-"
                col = "#ffe066" if cat == "net" else "#ffffff"
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=col, linewidth=lw, linestyle=ls, zorder=2)

            ax.set_xlim(-1.5, SPEC.doubles_width_m + 1.5)
            ax.set_ylim(SPEC.length_m + 2.5, -2.5)
            ax.set_aspect("equal")
            ax.tick_params(colors="#cbd5e1", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#475569")

        ax1 = axes[0]
        ax1.set_title("Ball Trajectory & Bounce Line Calls", color="#f8fafc", fontsize=11, pad=10)
        if self.ball_tracker.history:
            bx = [s.court_x_m for s in self.ball_tracker.history]
            by = [s.court_y_m for s in self.ball_tracker.history]
            ax1.plot(bx, by, color="#fde047", alpha=0.65, linewidth=1.5, zorder=3, label="Ball Flight")

        for b in self.bounce_judge.bounces:
            col = "#22c55e" if b.is_in else "#ef4444"
            edge = "#facc15" if b.in_doubt_zone else "#ffffff"
            ax1.scatter(
                [b.x_m],
                [b.y_m],
                s=95,
                c=col,
                edgecolors=edge,
                linewidths=1.8,
                zorder=5,
            )
            ax1.annotate(
                f"{b.call} ({b.signed_margin_cm:+.1f}cm)",
                (b.x_m, b.y_m),
                textcoords="offset points",
                xytext=(6, -6),
                color="#ffffff",
                fontsize=7.5,
                weight="bold",
                zorder=6,
            )

        ax2 = axes[1]
        ax2.set_title("Player Movement & Court Coverage", color="#f8fafc", fontsize=11, pad=10)
        for pid, p in self.player_tracker.tracks.items():
            if not p.court_history_m:
                continue
            pts = np.array(p.court_history_m)
            col = "#38bdf8" if pid == 1 else "#c084fc"
            ax2.plot(pts[:, 0], pts[:, 1], color=col, linewidth=2.0, alpha=0.85, zorder=4, label=p.label)
            ax2.scatter(pts[-1, 0], pts[-1, 1], s=80, color=col, edgecolors="#ffffff", zorder=5)
        ax2.legend(loc="upper right", facecolor="#1e293b", edgecolor="#475569", labelcolor="#f8fafc", fontsize=8)

        plt.tight_layout()
        Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_file), dpi=160, facecolor=fig.get_facecolor())
        plt.close(fig)