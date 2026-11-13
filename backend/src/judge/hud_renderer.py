"""Broadcast-grade HUD overlay: Virtual lines, ball comet trail, player boxes, 2D radar, and Hawk-Eye call card."""

from __future__ import annotations

from typing import Deque, Dict, List, Optional
import cv2
import numpy as np

from src.calibration.court_geometry import COURT_LINES_M, SPEC
from src.calibration.homography import CourtCalibrator
from src.calibration.virtual_court import VirtualCourtRenderer
from src.judge.bounce_judge import BounceEvent, StrokeEvent
from src.score.score_engine import TennisScoreEngine
from src.track.ball_tracker import BallState
from src.track.player_tracker import PlayerState


class BroadcastHUDRenderer:
    """Renders full CLEAR refereeing and analytics HUD onto a video frame."""

    def __init__(
        self,
        calibrator: CourtCalibrator,
        virtual_court: VirtualCourtRenderer,
    ) -> None:
        self.calibrator = calibrator
        self.virtual_court = virtual_court

    def render(
        self,
        frame_bgr: np.ndarray,
        frame_idx: int,
        ball_state: Optional[BallState],
        ball_trail: Deque[BallState],
        players: Dict[int, PlayerState],
        bounces: List[BounceEvent],
        strokes: List[StrokeEvent],
        score_engine: TennisScoreEngine,
        drift_px: float = 0.0,
        is_drifted: bool = False,
    ) -> np.ndarray:
        latest_bounce = bounces[-1] if bounces else None
        recent_bounce = (
            latest_bounce if (latest_bounce and frame_idx - latest_bounce.frame_idx <= 45) else None
        )

        # 1. Draw virtual court lines + highlight closest line when a bounce occurs
        canvas = self.virtual_court.draw(
            frame_bgr,
            draw_doubt_zone=True,
            draw_anchors=True,
            highlight_line=recent_bounce.closest_line if recent_bounce else None,
            highlight_is_in=recent_bounce.is_in if recent_bounce else None,
        )

        # 2. Draw historical bounce marks on the court surface
        self._draw_court_bounces(canvas, bounces, frame_idx)

        # 3. Draw players (bounding boxes, foot projection ellipse, speed & distance tag)
        self._draw_players(canvas, players)

        # 4. Draw glowing ball trajectory comet trail + current ball reticle
        self._draw_ball_trail(canvas, ball_state, ball_trail)

        # 5. Draw Top-Left Broadcast Scoreboard & Telemetry Bug
        self._draw_scoreboard_bug(
            canvas,
            score_engine=score_engine,
            ball_state=ball_state,
            strokes=strokes,
            drift_px=drift_px,
            is_drifted=is_drifted,
        )

        # 6. Draw Top-Right 2D Top-Down Court Minimap (Radar + Heatmap trails)
        self._draw_minimap(
            canvas,
            ball_state=ball_state,
            players=players,
            bounces=bounces,
        )

        # 7. Draw Bottom-Left Hawk-Eye Line Call Card + Doubt-Zone Magnifier
        if latest_bounce is not None:
            self._draw_line_call_card(canvas, frame_bgr, latest_bounce, frame_idx)

        return canvas

    def _draw_court_bounces(
        self,
        canvas: np.ndarray,
        bounces: List[BounceEvent],
        frame_idx: int,
    ) -> None:
        for b in bounces[-8:]:
            cx, cy = int(round(b.u)), int(round(b.v))
            color = (80, 245, 100) if b.is_in else (60, 65, 255)
            # Contact patch ellipse on clay
            cv2.ellipse(canvas, (cx, cy), (10, 5), 0, 0, 360, color, -1, cv2.LINE_AA)
            cv2.ellipse(canvas, (cx, cy), (12, 6), 0, 0, 360, (255, 255, 255), 1, cv2.LINE_AA)

            age = frame_idx - b.frame_idx
            if 0 <= age <= 30:
                ripple_r = int(12 + age * 1.4)
                cv2.ellipse(
                    canvas,
                    (cx, cy),
                    (ripple_r, max(4, ripple_r // 2)),
                    0,
                    0,
                    360,
                    (0, 215, 255) if b.in_doubt_zone else color,
                    2,
                    cv2.LINE_AA,
                )

    def _draw_players(self, canvas: np.ndarray, players: Dict[int, PlayerState]) -> None:
        for pid, p in players.items():
            x1, y1, x2, y2 = [int(round(v)) for v in p.bbox]
            fu, fv = int(round(p.foot_uv[0])), int(round(p.foot_uv[1]))
            color = (255, 195, 55) if pid == 1 else (180, 105, 255)

            # Tactical foot-ring on clay
            cv2.ellipse(
                canvas,
                (fu, fv),
                (int(max(14, (x2 - x1) * 0.55)), 7),
                0,
                0,
                360,
                color,
                2,
                cv2.LINE_AA,
            )

            # Corner-bracket bounding box
            bw, bh = x2 - x1, y2 - y1
            c_len = max(8, min(bw, bh) // 4)
            for cx, cy, dx, dy in [
                (x1, y1, 1, 1),
                (x2, y1, -1, 1),
                (x1, y2, 1, -1),
                (x2, y2, -1, -1),
            ]:
                cv2.line(canvas, (cx, cy), (cx + dx * c_len, cy), color, 2, cv2.LINE_AA)
                cv2.line(canvas, (cx, cy), (cx, cy + dy * c_len), color, 2, cv2.LINE_AA)

            # Label pill above player
            tag = f"{p.label} | {p.speed_kmh:.1f}km/h | {p.distance_m:.1f}m"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
            tx = max(6, min(canvas.shape[1] - tw - 12, fu - tw // 2))
            ty = max(th + 10, y1 - 8)
            cv2.rectangle(canvas, (tx - 5, ty - th - 5), (tx + tw + 5, ty + 4), (18, 22, 28), -1)
            cv2.rectangle(canvas, (tx - 5, ty - th - 5), (tx + tw + 5, ty + 4), color, 1)
            cv2.putText(
                canvas,
                tag,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (245, 248, 250),
                1,
                cv2.LINE_AA,
            )

    def _draw_ball_trail(
        self,
        canvas: np.ndarray,
        ball_state: Optional[BallState],
        ball_trail: Deque[BallState],
    ) -> None:
        pts = list(ball_trail)
        if len(pts) >= 2:
            for i in range(1, len(pts)):
                p_prev = pts[i - 1]
                p_curr = pts[i]
                if p_curr.frame_idx - p_prev.frame_idx > 6:
                    continue
                alpha = i / len(pts)
                thickness = max(1, int(round(alpha * 5)))
                # Gradient from warm orange to optic yellow-green
                color = (
                    int(40 + 40 * alpha),
                    int(165 + 90 * alpha),
                    255,
                )
                cv2.line(
                    canvas,
                    (int(round(p_prev.u)), int(round(p_prev.v))),
                    (int(round(p_curr.u)), int(round(p_curr.v))),
                    color,
                    thickness,
                    cv2.LINE_AA,
                )

        if ball_state is not None:
            bx, by = int(round(ball_state.u)), int(round(ball_state.v))
            cv2.circle(canvas, (bx, by), 9, (0, 245, 255), 2, cv2.LINE_AA)
            cv2.circle(canvas, (bx, by), 4, (255, 255, 255), -1, cv2.LINE_AA)

    def _draw_scoreboard_bug(
        self,
        canvas: np.ndarray,
        score_engine: TennisScoreEngine,
        ball_state: Optional[BallState],
        strokes: List[StrokeEvent],
        drift_px: float,
        is_drifted: bool,
    ) -> None:
        x0, y0, w_box, h_box = 18, 18, 370, 122
        sub = canvas[y0 : y0 + h_box, x0 : x0 + w_box]
        bg = np.full_like(sub, (18, 22, 29))
        canvas[y0 : y0 + h_box, x0 : x0 + w_box] = cv2.addWeighted(bg, 0.84, sub, 0.16, 0)
        cv2.rectangle(canvas, (x0, y0), (x0 + w_box, y0 + h_box), (65, 130, 215), 1)

        # Header bar
        cv2.rectangle(canvas, (x0, y0), (x0 + w_box, y0 + 26), (35, 78, 155), -1)
        cv2.putText(
            canvas,
            "CLEAR | CLAY-COURT AI REFEREE",
            (x0 + 10, y0 + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (245, 248, 255),
            1,
            cv2.LINE_AA,
        )
        drift_txt = f"DRIFT {drift_px:.1f}px"
        drift_col = (70, 80, 255) if is_drifted else (120, 240, 140)
        cv2.putText(
            canvas,
            drift_txt,
            (x0 + w_box - 98, y0 + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            drift_col,
            1,
            cv2.LINE_AA,
        )

        pt1, pt2 = score_engine.get_point_display()
        rows = [
            (score_engine.player1_name, score_engine.p1_sets, score_engine.p1_games, pt1, score_engine.server_id == 1),
            (score_engine.player2_name, score_engine.p2_sets, score_engine.p2_games, pt2, score_engine.server_id == 2),
        ]
        for idx, (name, s_val, g_val, p_val, is_srv) in enumerate(rows):
            ry = y0 + 52 + idx * 28
            if is_srv:
                cv2.circle(canvas, (x0 + 12, ry - 4), 4, (60, 240, 255), -1, cv2.LINE_AA)
            cv2.putText(
                canvas,
                name[:16],
                (x0 + 24, ry),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (235, 240, 245),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                str(s_val),
                (x0 + 235, ry),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (180, 205, 230),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                str(g_val),
                (x0 + 275, ry),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (240, 245, 250),
                1,
                cv2.LINE_AA,
            )
            cv2.rectangle(canvas, (x0 + 312, ry - 16), (x0 + 358, ry + 6), (40, 95, 185), -1)
            cv2.putText(
                canvas,
                p_val,
                (x0 + 322, ry),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        # Telemetry footer: Shot speed & Rally count
        spd = ball_state.speed_kmh if ball_state is not None else 0.0
        if strokes and spd < 10.0:
            spd = strokes[-1].shot_speed_kmh
        footer = f"BALL SPEED: {spd:5.1f} km/h   |   RALLY SHOTS: {len(strokes)}"
        cv2.putText(
            canvas,
            footer,
            (x0 + 12, y0 + 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (110, 225, 255),
            1,
            cv2.LINE_AA,
        )

    def _draw_minimap(
        self,
        canvas: np.ndarray,
        ball_state: Optional[BallState],
        players: Dict[int, PlayerState],
        bounces: List[BounceEvent],
    ) -> None:
        h_img, w_img = canvas.shape[:2]
        map_w, map_h = 156, 300
        margin = 18
        x0 = w_img - map_w - margin
        y0 = margin

        sub = canvas[y0 : y0 + map_h, x0 : x0 + map_w]
        bg = np.full_like(sub, (24, 34, 46))
        canvas[y0 : y0 + map_h, x0 : x0 + map_w] = cv2.addWeighted(bg, 0.86, sub, 0.14, 0)
        cv2.rectangle(canvas, (x0, y0), (x0 + map_w, y0 + map_h), (90, 145, 215), 1)

        pad_x, pad_y = 22, 26
        inner_w = map_w - 2 * pad_x
        inner_h = map_h - 2 * pad_y

        def to_mini(xm: float, ym: float) -> tuple[int, int]:
            u = int(round(x0 + pad_x + (xm / SPEC.doubles_width_m) * inner_w))
            v = int(round(y0 + pad_y + (ym / SPEC.length_m) * inner_h))
            return (
                int(np.clip(u, x0 + 3, x0 + map_w - 3)),
                int(np.clip(v, y0 + 3, y0 + map_h - 3)),
            )

        # Clay surface fill inside minimap
        c_tl = to_mini(0.0, 0.0)
        c_br = to_mini(SPEC.doubles_width_m, SPEC.length_m)
        cv2.rectangle(canvas, c_tl, c_br, (52, 92, 178), -1)

        # Draw court lines on minimap
        for name, p1, p2, cat in COURT_LINES_M:
            pt1 = to_mini(p1[0], p1[1])
            pt2 = to_mini(p2[0], p2[1])
            col = (100, 230, 255) if cat == "net" else (235, 240, 245)
            cv2.line(canvas, pt1, pt2, col, 1, cv2.LINE_AA)

        # Draw player movement trails + positions
        for pid, p in players.items():
            col = (255, 195, 55) if pid == 1 else (180, 105, 255)
            hist = p.court_history_m[-40:]
            for i in range(1, len(hist)):
                cv2.line(canvas, to_mini(*hist[i - 1]), to_mini(*hist[i]), col, 1, cv2.LINE_AA)
            px, py = to_mini(*p.court_xy_m)
            cv2.circle(canvas, (px, py), 5, col, -1, cv2.LINE_AA)
            cv2.circle(canvas, (px, py), 6, (255, 255, 255), 1, cv2.LINE_AA)

        # Draw historical bounces on minimap
        for b in bounces:
            bx, by = to_mini(b.x_m, b.y_m)
            b_col = (70, 245, 95) if b.is_in else (60, 60, 255)
            cv2.circle(canvas, (bx, by), 4, b_col, -1, cv2.LINE_AA)
            if b.in_doubt_zone:
                cv2.circle(canvas, (bx, by), 6, (0, 215, 255), 1, cv2.LINE_AA)

        # Draw current ball on minimap
        if ball_state is not None:
            bx, by = to_mini(ball_state.court_x_m, ball_state.court_y_m)
            cv2.circle(canvas, (bx, by), 4, (0, 255, 255), -1, cv2.LINE_AA)

        cv2.putText(
            canvas,
            "2D COURT RADAR",
            (x0 + 24, y0 + 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (220, 235, 250),
            1,
            cv2.LINE_AA,
        )

    def _draw_line_call_card(
        self,
        canvas: np.ndarray,
        raw_frame: np.ndarray,
        bounce: BounceEvent,
        frame_idx: int,
    ) -> None:
        h_img, w_img = canvas.shape[:2]
        card_w, card_h = 410, 118
        x0, y0 = 18, h_img - card_h - 18

        sub = canvas[y0 : y0 + card_h, x0 : x0 + card_w]
        bg = np.full_like(sub, (18, 22, 30))
        canvas[y0 : y0 + card_h, x0 : x0 + card_w] = cv2.addWeighted(bg, 0.88, sub, 0.12, 0)

        badge_col = (55, 200, 85) if bounce.is_in else (45, 55, 235)
        cv2.rectangle(canvas, (x0, y0), (x0 + card_w, y0 + card_h), badge_col, 2)

        # Call badge block on left
        cv2.rectangle(canvas, (x0, y0), (x0 + 104, y0 + card_h), badge_col, -1)
        call_x = x0 + 28 if bounce.is_in else x0 + 14
        cv2.putText(
            canvas,
            bounce.call,
            (call_x, y0 + 62),
            cv2.FONT_HERSHEY_DUPLEX,
            1.15,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"CONF {int(bounce.confidence * 100)}%",
            (x0 + 12, y0 + 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (240, 248, 255),
            1,
            cv2.LINE_AA,
        )

        # Margin & coordinates details
        sign_str = "+" if bounce.signed_margin_cm >= 0 else ""
        line1 = f"MARGIN: {sign_str}{bounce.signed_margin_cm:.1f} cm ({bounce.closest_line})"
        line2 = f"COURT XY: ({bounce.x_m:.2f}m, {bounce.y_m:.2f}m) | {bounce.speed_kmh:.1f} km/h"
        line3 = (
            "STATUS: DOUBT ZONE (<15cm) - CHALLENGE REPLAY"
            if bounce.in_doubt_zone
            else f"STATUS: CLEAR CALL (Frame #{bounce.frame_idx})"
        )
        col3 = (0, 215, 255) if bounce.in_doubt_zone else (175, 235, 195)

        cv2.putText(canvas, line1, (x0 + 116, y0 + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (250, 252, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, line2, (x0 + 116, y0 + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (195, 215, 235), 1, cv2.LINE_AA)
        cv2.putText(canvas, line3, (x0 + 116, y0 + 92), cv2.FONT_HERSHEY_SIMPLEX, 0.41, col3, 1, cv2.LINE_AA)

        # Inset Hawk-Eye Magnifier around bounce point when recent or in doubt zone
        if bounce.in_doubt_zone or (frame_idx - bounce.frame_idx <= 45):
            zoom_size = 118
            zx0 = x0 + card_w + 12
            zy0 = y0
            if zx0 + zoom_size < w_img - 10:
                bu, bv = int(round(bounce.u)), int(round(bounce.v))
                r = 28
                x1 = max(0, min(w_img - 2 * r, bu - r))
                y1 = max(0, min(h_img - 2 * r, bv - r))
                patch = canvas[y1 : y1 + 2 * r, x1 : x1 + 2 * r].copy()
                if patch.size > 0:
                    zoomed = cv2.resize(patch, (zoom_size, zoom_size), interpolation=cv2.INTER_LINEAR)
                    canvas[zy0 : zy0 + zoom_size, zx0 : zx0 + zoom_size] = zoomed
                    cv2.rectangle(
                        canvas,
                        (zx0, zy0),
                        (zx0 + zoom_size, zy0 + zoom_size),
                        (0, 215, 255) if bounce.in_doubt_zone else badge_col,
                        2,
                    )
                    cv2.putText(
                        canvas,
                        "HAWK-EYE ZOOM",
                        (zx0 + 8, zy0 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.38,
                        (255, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
