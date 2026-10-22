"""Zero-shot YOLO + 3-frame temporal motion/HSV hybrid detector for clay tennis courts."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Literal, Optional, Tuple
import cv2
import numpy as np

from src.calibration.homography import CourtCalibrator


@dataclass
class BallDetection:
    u: float
    v: float
    radius: float
    conf: float
    source: str = "hybrid"


@dataclass
class PlayerDetection:
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    conf: float
    foot_uv: Tuple[float, float]
    court_half: Literal["near", "far", "unknown"] = "unknown"
    source: str = "hybrid"


@dataclass
class FrameDetections:
    frame_idx: int
    balls: List[BallDetection] = field(default_factory=list)
    players: List[PlayerDetection] = field(default_factory=list)


class HybridTennisDetector:
    """Combines pretrained YOLO (when available) with 3-frame temporal + clay HSV segmentation."""

    def __init__(
        self,
        mode: Literal["hybrid", "yolo", "classical"] = "hybrid",
        yolo_weights: str = "yolov8n.pt",
        ball_conf_thresh: float = 0.20,
        player_conf_thresh: float = 0.35,
        ball_hsv_lower: Tuple[int, int, int] = (24, 95, 140),
        ball_hsv_upper: Tuple[int, int, int] = (46, 255, 255),
        min_ball_radius_px: int = 2,
        max_ball_radius_px: int = 18,
        use_3frame_temporal: bool = True,
    ) -> None:
        self.mode = mode
        self.yolo_weights = yolo_weights
        self.ball_conf_thresh = ball_conf_thresh
        self.player_conf_thresh = player_conf_thresh
        self.ball_hsv_lower = np.array(ball_hsv_lower, dtype=np.uint8)
        self.ball_hsv_upper = np.array(ball_hsv_upper, dtype=np.uint8)
        self.min_ball_radius_px = min_ball_radius_px
        self.max_ball_radius_px = max_ball_radius_px
        self.use_3frame_temporal = use_3frame_temporal

        self.gray_buffer: Deque[np.ndarray] = deque(maxlen=3)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=120, varThreshold=28, detectShadows=False
        )
        self.yolo_model = None
        if self.mode in ("hybrid", "yolo"):
            self._try_load_yolo()

    def _try_load_yolo(self) -> None:
        try:
            from pathlib import Path
            from ultralytics import YOLO  # type: ignore

            # Only auto-load if weights file exists locally or mode explicitly forces download
            if Path(self.yolo_weights).exists() or self.mode == "yolo":
                self.yolo_model = YOLO(self.yolo_weights)
        except Exception:
            self.yolo_model = None

    def detect(
        self,
        frame_bgr: np.ndarray,
        frame_idx: int,
        calibrator: Optional[CourtCalibrator] = None,
    ) -> FrameDetections:
        balls: List[BallDetection] = []
        players: List[PlayerDetection] = []

        # 1. Optional YOLO pass (COCO class 0 = person, class 32 = sports ball)
        if self.yolo_model is not None and self.mode in ("hybrid", "yolo"):
            try:
                results = self.yolo_model.predict(frame_bgr, verbose=False, conf=0.15)
                if results and len(results) > 0:
                    boxes = results[0].boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                        if cls_id == 32 and conf >= self.ball_conf_thresh:
                            u = 0.5 * (x1 + x2)
                            v = 0.5 * (y1 + y2)
                            r = 0.25 * ((x2 - x1) + (y2 - y1))
                            balls.append(BallDetection(u=u, v=v, radius=r, conf=conf, source="yolo"))
                        elif cls_id == 0 and conf >= self.player_conf_thresh:
                            foot_u = 0.5 * (x1 + x2)
                            foot_v = y2
                            half = self._classify_half(foot_u, foot_v, frame_bgr.shape[0], calibrator)
                            players.append(
                                PlayerDetection(
                                    bbox=(x1, y1, x2, y2),
                                    conf=conf,
                                    foot_uv=(foot_u, foot_v),
                                    court_half=half,
                                    source="yolo",
                                )
                            )
            except Exception:
                pass

        # 2. Classical 3-Frame Temporal + HSV Clay-Court Detector
        if self.mode in ("hybrid", "classical") or (not balls and not players):
            c_balls, c_players = self._detect_classical(frame_bgr, calibrator)
            # Merge balls (deduplicate within 15px)
            for cb in c_balls:
                if not any(np.hypot(cb.u - b.u, cb.v - b.v) < 15.0 for b in balls):
                    balls.append(cb)
            # Merge players (deduplicate overlapping boxes)
            for cp in c_players:
                if not any(self._iou(cp.bbox, p.bbox) > 0.35 for p in players):
                    players.append(cp)

        balls.sort(key=lambda b: b.conf, reverse=True)
        players.sort(key=lambda p: p.conf, reverse=True)
        return FrameDetections(frame_idx=frame_idx, balls=balls, players=players)

    def _detect_classical(
        self,
        frame_bgr: np.ndarray,
        calibrator: Optional[CourtCalibrator] = None,
    ) -> Tuple[List[BallDetection], List[PlayerDetection]]:
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        self.gray_buffer.append(gray)

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        fg_mask = self.bg_subtractor.apply(frame_bgr)

        # --- Ball detection: Optic yellow HSV + optional 3-frame motion boost ---
        color_mask = cv2.inRange(hsv, self.ball_hsv_lower, self.ball_hsv_upper)
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel_small)
        color_mask = cv2.dilate(color_mask, kernel_small, iterations=1)

        motion_mask = np.zeros_like(gray)
        if self.use_3frame_temporal and len(self.gray_buffer) >= 2:
            d1 = cv2.absdiff(self.gray_buffer[-1], self.gray_buffer[-2])
            _, m1 = cv2.threshold(d1, 12, 255, cv2.THRESH_BINARY)
            if len(self.gray_buffer) == 3:
                d2 = cv2.absdiff(self.gray_buffer[-1], self.gray_buffer[0])
                _, m2 = cv2.threshold(d2, 12, 255, cv2.THRESH_BINARY)
                motion_mask = cv2.bitwise_or(m1, m2)
            else:
                motion_mask = m1
            motion_mask = cv2.dilate(motion_mask, kernel_small, iterations=2)

        balls: List[BallDetection] = []
        contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 4 or area > np.pi * (self.max_ball_radius_px**2) * 1.6:
                continue
            (cx, cy), radius = cv2.minEnclosingCircle(cnt)
            if radius < self.min_ball_radius_px or radius > self.max_ball_radius_px:
                continue
            perimeter = max(cv2.arcLength(cnt, True), 1e-3)
            circularity = 4.0 * np.pi * area / (perimeter * perimeter)
            if circularity < 0.35:
                continue

            ix, iy = int(np.clip(cx, 0, w - 1)), int(np.clip(cy, 0, h - 1))
            has_motion = bool(motion_mask[iy, ix] > 0) if len(self.gray_buffer) >= 2 else True
            # Score candidate by circularity + motion energy + HSV saturation/value
            sat_val = float(hsv[iy, ix, 1]) / 255.0 * 0.5 + float(hsv[iy, ix, 2]) / 255.0 * 0.5
            conf = 0.45 * min(1.0, circularity) + 0.30 * sat_val + (0.23 if has_motion else 0.05)
            if conf >= self.ball_conf_thresh:
                balls.append(
                    BallDetection(
                        u=float(cx),
                        v=float(cy),
                        radius=float(radius),
                        conf=round(float(min(0.98, conf)), 3),
                        source="temporal_hsv" if has_motion else "hsv",
                    )
                )

        # --- Player detection: Apparel/skin/motion blobs in court region ---
        # Detect distinct non-clay figures (high contrast against clay hue ~5-18)
        # Clay court background typically has H in [4, 18], S in [80, 210], V in [90, 215]
        clay_mask = cv2.inRange(hsv, np.array([4, 65, 70], dtype=np.uint8), np.array([19, 235, 230], dtype=np.uint8))
        non_clay = cv2.bitwise_not(clay_mask)
        # Exclude bright white court lines and small ball blobs
        bright_lines = cv2.inRange(hsv, np.array([0, 0, 210], dtype=np.uint8), np.array([180, 45, 255], dtype=np.uint8))
        figure_mask = cv2.bitwise_and(non_clay, cv2.bitwise_not(bright_lines))
        figure_mask = cv2.bitwise_and(figure_mask, cv2.bitwise_not(color_mask))

        # Combine with foreground motion mask inside the court arena
        arena_mask = np.zeros_like(gray)
        arena_mask[int(h * 0.10) : int(h * 0.96), int(w * 0.06) : int(w * 0.94)] = 255
        combined_player = cv2.bitwise_and(cv2.bitwise_or(fg_mask, figure_mask), arena_mask)

        kernel_vert = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 15))
        combined_player = cv2.morphologyEx(combined_player, cv2.MORPH_CLOSE, kernel_vert)
        combined_player = cv2.morphologyEx(
            combined_player, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        )

        players: List[PlayerDetection] = []
        p_contours, _ = cv2.findContours(combined_player, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in p_contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            aspect = bh / max(bw, 1)
            # Far-court player is smaller (~28-75px tall), near-court player is taller (~50-150px)
            if bh < 24 or bh > int(h * 0.42) or bw < 10 or bw > int(w * 0.22):
                continue
            if aspect < 1.05 or aspect > 4.2 or area < 300:
                continue

            foot_u = float(x + bw * 0.5)
            foot_v = float(y + bh)
            half = self._classify_half(foot_u, foot_v, h, calibrator)
            if half == "unknown":
                continue

            conf = float(np.clip(0.55 + 0.25 * min(1.0, area / 2800.0), 0.40, 0.94))
            players.append(
                PlayerDetection(
                    bbox=(float(x), float(y), float(x + bw), float(y + bh)),
                    conf=round(conf, 3),
                    foot_uv=(foot_u, foot_v),
                    court_half=half,
                    source="classical",
                )
            )

        return balls, players

    @staticmethod
    def _classify_half(
        u: float,
        v: float,
        img_h: int,
        calibrator: Optional[CourtCalibrator],
    ) -> Literal["near", "far", "unknown"]:
        if calibrator is not None and calibrator.H_img_to_court is not None:
            x_m, y_m = calibrator.point_image_to_court(u, v)
            if -3.5 <= x_m <= 14.5 and -4.5 <= y_m <= 28.5:
                return "far" if y_m < 11.885 else "near"
            return "unknown"
        return "far" if v < img_h * 0.48 else "near"

    @staticmethod
    def _iou(
        b1: Tuple[float, float, float, float],
        b2: Tuple[float, float, float, float],
    ) -> float:
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        a1 = max(1.0, (b1[2] - b1[0]) * (b1[3] - b1[1]))
        a2 = max(1.0, (b2[2] - b2[0]) * (b2[3] - b2[1]))
        return inter / (a1 + a2 - inter + 1e-6)
