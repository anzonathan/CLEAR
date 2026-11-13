"""Virtual court overlay renderer for clay courts with worn or rain-wiped lines."""

from __future__ import annotations

from typing import Literal, Optional, Tuple
import cv2
import numpy as np

from .court_geometry import ANCHOR_COORDS_M, COURT_LINES_M, SPEC, get_active_bounds
from .homography import CourtCalibrator


class VirtualCourtRenderer:
    """Projects ITF court geometry through the homography and draws virtual lines + doubt zones."""

    def __init__(
        self,
        calibrator: CourtCalibrator,
        court_mode: Literal["singles", "doubles"] = "singles",
        doubt_zone_cm: float = 15.0,
    ) -> None:
        self.calibrator = calibrator
        self.court_mode = court_mode
        self.doubt_zone_cm = doubt_zone_cm

    def draw(
        self,
        frame_bgr: np.ndarray,
        draw_doubt_zone: bool = True,
        draw_anchors: bool = True,
        highlight_line: Optional[str] = None,
        highlight_is_in: Optional[bool] = None,
    ) -> np.ndarray:
        """Render virtual court lines, doubt zone ribbon, and anchor pegs onto frame."""
        if self.calibrator.H_court_to_img is None:
            return frame_bgr

        out = frame_bgr.copy()
        overlay = frame_bgr.copy()

        # 1. Subtle court surface tint inside active play area
        x_min, x_max, y_min, y_max, _ = get_active_bounds(self.court_mode, "full")
        active_poly_m = np.array(
            [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
            dtype=np.float64,
        )
        active_poly_px = np.round(self.calibrator.court_to_image(active_poly_m)).astype(np.int32)
        cv2.fillPoly(overlay, [active_poly_px], (48, 95, 195))  # Subtle warm clay highlight

        # 2. Optional +/- 15cm Doubt Zone band along active baselines and sidelines
        if draw_doubt_zone:
            dz_m = self.doubt_zone_cm / 100.0
            outer_poly_m = np.array(
                [
                    [x_min - dz_m, y_min - dz_m],
                    [x_max + dz_m, y_min - dz_m],
                    [x_max + dz_m, y_max + dz_m],
                    [x_min - dz_m, y_max + dz_m],
                ],
                dtype=np.float64,
            )
            inner_poly_m = np.array(
                [
                    [x_min + dz_m, y_min + dz_m],
                    [x_max - dz_m, y_min + dz_m],
                    [x_max - dz_m, y_max - dz_m],
                    [x_min + dz_m, y_max - dz_m],
                ],
                dtype=np.float64,
            )
            outer_px = np.round(self.calibrator.court_to_image(outer_poly_m)).astype(np.int32)
            inner_px = np.round(self.calibrator.court_to_image(inner_poly_m)).astype(np.int32)

            dz_layer = out.copy()
            cv2.fillPoly(dz_layer, [outer_px], (0, 215, 255))
            cv2.fillPoly(dz_layer, [inner_px], (0, 0, 0))
            mask = np.zeros(out.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [outer_px], 255)
            cv2.fillPoly(mask, [inner_px], 0)
            out[mask > 0] = cv2.addWeighted(out, 0.80, dz_layer, 0.20, 0)[mask > 0]

        out = cv2.addWeighted(overlay, 0.08, out, 0.92, 0)

        # 3. Draw every regulation court line
        glow_layer = out.copy()
        for name, p1_m, p2_m, category in COURT_LINES_M:
            pts_px = self.calibrator.court_to_image([p1_m, p2_m])
            pt1 = (int(round(pts_px[0, 0])), int(round(pts_px[0, 1])))
            pt2 = (int(round(pts_px[1, 0])), int(round(pts_px[1, 1])))

            is_highlighted = highlight_line == name
            if is_highlighted:
                color = (90, 250, 90) if highlight_is_in else (60, 60, 255)
                thickness = 4
                cv2.line(glow_layer, pt1, pt2, color, 10, cv2.LINE_AA)
            elif category == "net":
                color = (255, 220, 110)  # Cyan-gold net line
                thickness = 2
            elif category == "doubles" and self.court_mode == "singles":
                color = (175, 195, 210)  # Dimmed doubles alley in singles mode
                thickness = 1
            elif category in ("baseline", "singles", "doubles"):
                color = (240, 255, 255)  # High-contrast virtual line
                thickness = 2
            else:
                color = (220, 240, 240)
                thickness = 2

            cv2.line(out, pt1, pt2, color, thickness, cv2.LINE_AA)

        out = cv2.addWeighted(glow_layer, 0.30, out, 0.70, 0)

        # 4. Draw physical calibration anchor markers
        if draw_anchors:
            for name, (u, v) in self.calibrator.anchors_px.items():
                px, py = int(round(u)), int(round(v))
                cv2.circle(out, (px, py), 7, (0, 210, 255), 2, cv2.LINE_AA)
                cv2.circle(out, (px, py), 2, (255, 255, 255), -1, cv2.LINE_AA)

        return out
