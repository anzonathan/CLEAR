"""Generates realistic UCU clay-court rally videos with 3D ball physics, clay dust at bounce, and exact ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Tuple
import cv2
import numpy as np

from src.calibration.court_geometry import COURT_LINES_M, SPEC, evaluate_court_point
from src.calibration.homography import CourtCalibrator

# Half stance width in metres (left/right foot offset from mid-foot)
_FOOT_HALF_WIDTH_M = 0.12


def generate_synthetic_clay_rally(
    video_path: str | Path,
    gt_json_path: str | Path | None = None,
    calib_json_path: str | Path | None = None,
    width: int = 1280,
    height: int = 720,
    fps: float = 60.0,
    line_condition: Literal["fresh", "worn", "wiped"] = "worn",
) -> Dict[str, object]:
    """Create a realistic clay-court rally video with ground-truth ball/player tracks and bounces."""
    out_video = Path(video_path)
    out_video.parent.mkdir(parents=True, exist_ok=True)

    calibrator = CourtCalibrator.from_default_camera_geometry(width=width, height=height)
    if calib_json_path is not None:
        calibrator.save(calib_json_path)

    # Pre-render static clay court background with specified line wear condition
    base_bg = _build_clay_background(width, height, calibrator, line_condition=line_condition)

    # Define 4 rally arcs: (start_frame, bounce_frame, end_frame, p_start_m, p_bounce_m, p_end_m, hitter_id)
    # Court X in [0..10.97], Singles X in [1.37..9.60], Court Y in [0..23.77] (Net = 11.885)
    rally_segments = [
        # Shot 1: P1 (Near) hits cross-court to Far court (IN, comfortable margin)
        {
            "f_start": 8,
            "f_bounce": 46,
            "f_end": 68,
            "start_m": (6.60, 22.80),
            "bounce_m": (3.10, 3.40),
            "end_m": (2.35, 1.15),
            "peak_z_m": 2.15,
            "rebound_z_m": 1.15,
            "hitter_id": 1,
        },
        # Shot 2: P2 (Far) hits sharp cross-court angle near right singles sideline (IN, Doubt Zone ~+7cm)
        {
            "f_start": 68,
            "f_bounce": 110,
            "f_end": 134,
            "start_m": (2.35, 1.15),
            "bounce_m": (9.59, 19.65),  # Right singles line is at x = 9.60m -> Doubt Zone IN!
            "end_m": (9.85, 22.90),
            "peak_z_m": 2.05,
            "rebound_z_m": 1.10,
            "hitter_id": 2,
        },
        # Shot 3: P1 (Near) hits down-the-line deep to Far baseline (IN, ~+45cm inside baseline)
        {
            "f_start": 134,
            "f_bounce": 176,
            "f_end": 198,
            "start_m": (9.85, 22.90),
            "bounce_m": (8.10, 0.45),
            "end_m": (7.40, -1.65),
            "peak_z_m": 2.35,
            "rebound_z_m": 1.45,
            "hitter_id": 1,
        },
        # Shot 4: P2 (Far) attempts deep cross-court winner -> lands OUT long past Near baseline (~-17cm OUT)
        {
            "f_start": 198,
            "f_bounce": 242,
            "f_end": 268,
            "start_m": (7.40, -1.65),
            "bounce_m": (3.20, 23.98),  # Near baseline is at y = 23.77m -> OUT long!
            "end_m": (2.60, 25.40),
            "peak_z_m": 2.30,
            "rebound_z_m": 0.95,
            "hitter_id": 2,
        },
    ]

    total_frames = 280
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_video), fourcc, fps, (width, height))

    gt_frames: List[Dict[str, object]] = []
    gt_bounces: List[Dict[str, object]] = []

    for seg in rally_segments:
        bx, by = seg["bounce_m"]
        half: Literal["near", "far"] = "far" if by < SPEC.net_y_m else "near"
        ev = evaluate_court_point(bx, by, mode="singles", target_half=half)
        b_uv = calibrator.point_court_to_image(bx, by)
        gt_bounces.append(
            {
                "frame_idx": seg["f_bounce"],
                "u": round(b_uv[0], 2),
                "v": round(b_uv[1], 2),
                "x_m": round(bx, 3),
                "y_m": round(by, 3),
                "call": ev["call"],
                "is_in": ev["is_in"],
                "signed_margin_cm": ev["signed_margin_cm"],
                "in_doubt_zone": ev["in_doubt_zone"],
                "closest_line": ev["closest_line"],
                "court_half": half,
            }
        )

    for f in range(total_frames):
        frame = base_bg.copy()

        # Dual-foot positions in court metres
        (p1_left_m, p1_right_m), (p2_left_m, p2_right_m) = _interpolate_players(f, rally_segments)

        # Project all four feet to image pixels
        p1_left_px = calibrator.point_court_to_image(*p1_left_m)
        p1_right_px = calibrator.point_court_to_image(*p1_right_m)
        p2_left_px = calibrator.point_court_to_image(*p2_left_m)
        p2_right_px = calibrator.point_court_to_image(*p2_right_m)

        # Mid-foot (kept for backward compatibility with existing tracker/stats)
        p1_mid_m = (
            0.5 * (p1_left_m[0] + p1_right_m[0]),
            0.5 * (p1_left_m[1] + p1_right_m[1]),
        )
        p2_mid_m = (
            0.5 * (p2_left_m[0] + p2_right_m[0]),
            0.5 * (p2_left_m[1] + p2_right_m[1]),
        )

        # Draw Far Player first (painter's order)
        _draw_player_sprite(
            frame,
            left_foot_px=p2_left_px,
            right_foot_px=p2_right_px,
            scale=0.62,
            kit_bgr=(215, 95, 165),
            shorts_bgr=(45, 35, 55),
        )

        # Compute ball state for frame f
        ball_info = _interpolate_ball_3d(f, rally_segments, calibrator)

        # Draw dust puff on clay if within 12 frames after a bounce
        for gb in gt_bounces:
            dt_b = f - int(gb["frame_idx"])
            if 0 <= dt_b <= 14:
                du, dv = int(round(float(gb["u"]))), int(round(float(gb["v"])))
                dust_layer = frame.copy()
                r_dust = int(5 + dt_b * 1.1)
                cv2.ellipse(
                    dust_layer,
                    (du, dv),
                    (r_dust, max(3, r_dust // 2)),
                    0,
                    0,
                    360,
                    (145, 175, 215),
                    -1,
                    cv2.LINE_AA,
                )
                alpha_d = max(0.05, 0.38 * (1.0 - dt_b / 15.0))
                frame = cv2.addWeighted(dust_layer, alpha_d, frame, 1.0 - alpha_d, 0)

        # Draw tennis ball + ground shadow
        if ball_info is not None:
            bu, bv, shadow_u, shadow_v, radius_px, bx_m, by_m = ball_info
            # Ground shadow on clay (helps visual realism)
            cv2.ellipse(
                frame,
                (int(round(shadow_u)), int(round(shadow_v))),
                (max(3, int(radius_px)), max(2, int(radius_px * 0.5))),
                0,
                0,
                360,
                (45, 65, 115),
                -1,
                cv2.LINE_AA,
            )
            # Optic yellow-green tennis ball
            cv2.circle(
                frame,
                (int(round(bu)), int(round(bv))),
                int(round(radius_px)),
                (42, 238, 245),
                -1,
                cv2.LINE_AA,
            )
            cv2.circle(
                frame,
                (int(round(bu - 1)), int(round(bv - 1))),
                max(1, int(round(radius_px * 0.45))),
                (140, 255, 255),
                -1,
                cv2.LINE_AA,
            )

            gt_frames.append(
                {
                    "frame_idx": f,
                    "ball_u": round(bu, 2),
                    "ball_v": round(bv, 2),
                    "ball_x_m": round(bx_m, 3),
                    "ball_y_m": round(by_m, 3),
                    # Dual feet (court metres)
                    "p1_left_foot_xy_m": [round(p1_left_m[0], 3), round(p1_left_m[1], 3)],
                    "p1_right_foot_xy_m": [round(p1_right_m[0], 3), round(p1_right_m[1], 3)],
                    "p2_left_foot_xy_m": [round(p2_left_m[0], 3), round(p2_left_m[1], 3)],
                    "p2_right_foot_xy_m": [round(p2_right_m[0], 3), round(p2_right_m[1], 3)],
                    # Mid-foot kept for backward compatibility
                    "p1_xy_m": [round(p1_mid_m[0], 3), round(p1_mid_m[1], 3)],
                    "p2_xy_m": [round(p2_mid_m[0], 3), round(p2_mid_m[1], 3)],
                }
            )

        # Draw Near Player
        _draw_player_sprite(
            frame,
            left_foot_px=p1_left_px,
            right_foot_px=p1_right_px,
            scale=1.05,
            kit_bgr=(210, 145, 30),
            shorts_bgr=(35, 40, 50),
        )

        writer.write(frame)

    writer.release()

    gt_payload = {
        "video_path": str(out_video),
        "width": width,
        "height": height,
        "fps": fps,
        "line_condition": line_condition,
        "anchors_px": {k: list(v) for k, v in calibrator.anchors_px.items()},
        "bounces": gt_bounces,
        "frames": gt_frames,
    }
    if gt_json_path is not None:
        Path(gt_json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(gt_json_path).write_text(json.dumps(gt_payload, indent=2), encoding="utf-8")

    return gt_payload


def _build_clay_background(
    width: int,
    height: int,
    calibrator: CourtCalibrator,
    line_condition: Literal["fresh", "worn", "wiped"] = "worn",
) -> np.ndarray:
    rng = np.random.default_rng(42)
    # Surrounding court apron (muted terracotta-brown)
    bg = np.full((height, width, 3), (72, 96, 158), dtype=np.uint8)

    # Top stadium/trees backdrop above horizon
    horizon_y = int(height * 0.14)
    bg[:horizon_y, :] = (52, 78, 62)

    # Inner clay court polygon
    court_poly_m = np.array(
        [
            [-1.2, -2.0],
            [SPEC.doubles_width_m + 1.2, -2.0],
            [SPEC.doubles_width_m + 1.2, SPEC.length_m + 2.2],
            [-1.2, SPEC.length_m + 2.2],
        ],
        dtype=np.float64,
    )
    court_poly_px = np.round(calibrator.court_to_image(court_poly_m)).astype(np.int32)
    cv2.fillPoly(bg, [court_poly_px], (68, 108, 188))  # Classic red-ochre clay BGR

    # Add fine granular clay texture
    noise = rng.integers(-9, 10, size=(height, width, 3), dtype=np.int16)
    bg = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Draw painted court lines according to `line_condition`
    if line_condition != "wiped":
        line_layer = bg.copy()
        for name, p1, p2, cat in COURT_LINES_M:
            if cat == "net":
                continue
            pts_px = calibrator.court_to_image([p1, p2])
            pt1 = (int(round(pts_px[0, 0])), int(round(pts_px[0, 1])))
            pt2 = (int(round(pts_px[1, 0])), int(round(pts_px[1, 1])))
            cv2.line(line_layer, pt1, pt2, (215, 222, 232), 2, cv2.LINE_AA)

        if line_condition == "fresh":
            bg = cv2.addWeighted(line_layer, 0.85, bg, 0.15, 0)
        elif line_condition == "worn":
            # Simulate clay dust patches partially obscuring painted lines
            wear_mask = rng.uniform(0.0, 1.0, size=(height // 8, width // 8)).astype(np.float32)
            wear_mask = cv2.resize(wear_mask, (width, height), interpolation=cv2.INTER_LINEAR)
            alpha = (wear_mask > 0.55).astype(np.float32) * 0.35
            bg = (line_layer * alpha[..., None] + bg * (1.0 - alpha[..., None])).astype(np.uint8)

    # Draw physical net & net posts
    net_pts = calibrator.court_to_image([(0.0, SPEC.net_y_m), (SPEC.doubles_width_m, SPEC.net_y_m)])
    nl = (int(round(net_pts[0, 0])), int(round(net_pts[0, 1])))
    nr = (int(round(net_pts[1, 0])), int(round(net_pts[1, 1])))
    cv2.line(bg, (nl[0], nl[1] - 26), (nr[0], nr[1] - 26), (235, 235, 235), 2, cv2.LINE_AA)
    cv2.line(bg, nl, (nl[0], nl[1] - 28), (50, 55, 60), 4, cv2.LINE_AA)
    cv2.line(bg, nr, (nr[0], nr[1] - 28), (50, 55, 60), 4, cv2.LINE_AA)

    # Draw physical anchor pegs at the 4 doubles corners
    for k, (u, v) in calibrator.anchors_px.items():
        cv2.circle(bg, (int(round(u)), int(round(v))), 4, (235, 245, 255), -1, cv2.LINE_AA)

    return bg


def _split_feet(mid_xy_m: Tuple[float, float]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Return (left_foot_xy_m, right_foot_xy_m) from a mid-foot position."""
    x, y = mid_xy_m
    left = (x - _FOOT_HALF_WIDTH_M, y)
    right = (x + _FOOT_HALF_WIDTH_M, y)
    return left, right


def _interpolate_players(
    frame_idx: int,
    segments: List[Dict[str, object]],
) -> Tuple[
    Tuple[Tuple[float, float], Tuple[float, float]],
    Tuple[Tuple[float, float], Tuple[float, float]],
]:
    """Return ((p1_left, p1_right), (p2_left, p2_right)) in court metres."""
    # Keyframes for mid-foot of P1 (Near) and P2 (Far)
    p1_keys = [
        (0, (6.60, 22.80)),
        (46, (5.80, 23.00)),
        (110, (8.30, 23.30)),
        (134, (9.85, 22.90)),
        (198, (6.40, 22.50)),
        (268, (4.20, 23.20)),
        (300, (4.20, 23.20)),
    ]
    p2_keys = [
        (0, (4.50, 1.00)),
        (46, (2.30, 0.90)),
        (68, (2.35, 1.15)),
        (134, (5.50, -0.40)),
        (176, (6.40, -1.45)),
        (198, (7.40, -1.65)),
        (268, (5.60, 0.60)),
        (300, (5.60, 0.60)),
    ]
    p1_mid = _interp_path(frame_idx, p1_keys)
    p2_mid = _interp_path(frame_idx, p2_keys)
    return _split_feet(p1_mid), _split_feet(p2_mid)


def _interp_path(
    frame_idx: int,
    keys: List[Tuple[int, Tuple[float, float]]],
) -> Tuple[float, float]:
    for i in range(len(keys) - 1):
        f0, p0 = keys[i]
        f1, p1 = keys[i + 1]
        if f0 <= frame_idx <= f1:
            t = (frame_idx - f0) / max(1, f1 - f0)
            # Smoothstep easing for natural player acceleration/deceleration
            s = t * t * (3.0 - 2.0 * t)
            return (p0[0] + s * (p1[0] - p0[0]), p0[1] + s * (p1[1] - p0[1]))
    return keys[-1][1]


def _interpolate_ball_3d(
    frame_idx: int,
    segments: List[Dict[str, object]],
    calibrator: CourtCalibrator,
) -> Tuple[float, float, float, float, float, float, float] | None:
    for seg in segments:
        f_start = int(seg["f_start"])
        f_bounce = int(seg["f_bounce"])
        f_end = int(seg["f_end"])
        if not (f_start <= frame_idx <= f_end):
            continue

        s_m = seg["start_m"]
        b_m = seg["bounce_m"]
        e_m = seg["end_m"]
        peak_z = float(seg["peak_z_m"])
        reb_z = float(seg["rebound_z_m"])

        if frame_idx <= f_bounce:
            t = (frame_idx - f_start) / max(1, f_bounce - f_start)
            xm = s_m[0] + t * (b_m[0] - s_m[0])
            ym = s_m[1] + t * (b_m[1] - s_m[1])
            # Parabolic height arc hitting z = 0.0 exactly at t = 1.0 (f_bounce)
            zm = max(0.0, 4.0 * peak_z * t * (1.0 - t) + 0.95 * (1.0 - t) * (1.0 - t))
        else:
            t = (frame_idx - f_bounce) / max(1, f_end - f_bounce)
            xm = b_m[0] + t * (e_m[0] - b_m[0])
            ym = b_m[1] + t * (e_m[1] - b_m[1])
            # Rebound arc rising from z = 0.0 at t = 0.0
            zm = max(0.0, reb_z * np.sin(0.75 * np.pi * t))

        shadow_u, shadow_v = calibrator.point_court_to_image(xm, ym)
        # Perspective height scale (pixels per metre of altitude increases towards near camera)
        depth_factor = 25.0 + 20.0 * (ym / SPEC.length_m)
        bu = shadow_u
        bv = shadow_v - zm * depth_factor
        radius_px = float(np.clip(3.8 + 2.8 * (ym / SPEC.length_m), 3.5, 7.5))
        return bu, bv, shadow_u, shadow_v, radius_px, xm, ym

    return None


def _draw_player_sprite(
    frame: np.ndarray,
    left_foot_px: Tuple[float, float],
    right_foot_px: Tuple[float, float],
    scale: float,
    kit_bgr: Tuple[int, int, int],
    shorts_bgr: Tuple[int, int, int],
) -> None:
    """Draw player with independent left and right foot contact points."""
    lu, lv = float(left_foot_px[0]), float(left_foot_px[1])
    ru, rv = float(right_foot_px[0]), float(right_foot_px[1])

    # Midpoint between the two feet (used for torso / head alignment)
    u = int(round(0.5 * (lu + ru)))
    v = int(round(0.5 * (lv + rv)))

    h_tot = int(round(76 * scale))
    w_torso = int(round(20 * scale))
    leg_h = int(h_tot * 0.42)

    # Shadow under both feet
    cv2.ellipse(
        frame,
        (u, v),
        (int(16 * scale), int(6 * scale)),
        0, 0, 360,
        (42, 62, 105),
        -1,
        cv2.LINE_AA,
    )

    # Left leg → left foot
    cv2.line(
        frame,
        (int(round(lu)), int(round(lv))),
        (u - int(4 * scale), v - leg_h),
        (95, 120, 165),
        max(2, int(4 * scale)),
        cv2.LINE_AA,
    )
    # Right leg → right foot
    cv2.line(
        frame,
        (int(round(ru)), int(round(rv))),
        (u + int(4 * scale), v - leg_h),
        (95, 120, 165),
        max(2, int(4 * scale)),
        cv2.LINE_AA,
    )

    # Shorts
    shorts_top = v - int(h_tot * 0.54)
    cv2.rectangle(
        frame,
        (u - w_torso // 2, shorts_top),
        (u + w_torso // 2, v - int(h_tot * 0.36)),
        shorts_bgr,
        -1,
    )

    # Jersey / torso
    torso_top = v - int(h_tot * 0.84)
    cv2.rectangle(
        frame,
        (u - w_torso // 2, torso_top),
        (u + w_torso // 2, shorts_top),
        kit_bgr,
        -1,
    )

    # Head
    head_r = max(4, int(round(8 * scale)))
    cv2.circle(
        frame,
        (u, torso_top - head_r),
        head_r,
        (95, 120, 165),
        -1,
        cv2.LINE_AA,
    )