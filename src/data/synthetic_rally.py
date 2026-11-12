"""Generates realistic UCU clay-court rally videos with 3D ball physics, clay dust at bounce, and exact ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np

from src.calibration.court_geometry import COURT_LINES_M, SPEC, evaluate_court_point, get_active_bounds
from src.calibration.homography import CourtCalibrator

# Half stance width in metres (left/right foot offset from mid-foot)
_FOOT_HALF_WIDTH_M = 0.12

# ---------------------------------------------------------------------------
# Serve timing (frames, RELATIVE to the first frame of a serve window).
# Increased for more natural pacing.
# ---------------------------------------------------------------------------
SERVE_START_FRAME = 0
SERVE_TOSS_FRAME = 12
SERVE_CONTACT_FRAME = 32
SERVE_FLIGHT_FRAMES = 38
SERVE_BOUNCE_FRAME = SERVE_CONTACT_FRAME + SERVE_FLIGHT_FRAMES   # 70
SERVE_END_FRAME = SERVE_BOUNCE_FRAME + 18                        # 88
SERVE_RESET_GAP_FRAMES = 25

_SERVE_END_FRAME = SERVE_END_FRAME
_SERVE_CONTACT_FRAME = SERVE_CONTACT_FRAME
# Frame (relative) at which the faulting foot reaches the baseline. Must be < contact.
_SERVE_FAULT_START = 18

_SERVE_START_Z_M = 2.60
_SERVE_PEAK_Z_M = 1.60
_SERVE_STANCE_Y_M = 24.30
_SERVE_STEP_IN_Y_M = 23.40
_SERVE_FAULT_FOOT_Y_M = 23.70

ServeOutcome = Literal[
    "legal",
    "long",
    "wide",
    "wrong_service_box",
    "let",
]


def _serve_target_box(service_side: str) -> tuple[float, float, float, float]:
    if service_side == "right":
        mode = "service_far_left"
    elif service_side == "left":
        mode = "service_far_right"
    else:
        raise ValueError("service_side must be 'right' or 'left'")

    x_min, x_max, y_min, y_max, _ = get_active_bounds(mode=mode)
    return x_min, x_max, y_min, y_max


def _side_sign(service_side: str) -> float:
    return 1.0 if service_side == "right" else -1.0


def _serve_stance_mid_x(service_side: str) -> float:
    return SPEC.center_x_m + _side_sign(service_side) * 0.915


def _make_serve_segment(
    service_side: str = "right",
    outcome: ServeOutcome = "legal",
    start_frame: int = SERVE_START_FRAME,
    foot_fault: bool = False,
) -> dict:
    x_min, x_max, y_min, y_max = _serve_target_box(service_side)
    box_cx = 0.5 * (x_min + x_max)
    box_cy = 0.5 * (y_min + y_max)

    if outcome in ("legal", "let"):
        bounce = (box_cx, box_cy)

    elif outcome == "wrong_service_box":
        # Clearly in the opposite service box
        bounce = (2.0 * SPEC.center_x_m - box_cx, box_cy)

    elif outcome == "wide":
        # 1.30 m outside the singles sideline (very obvious)
        if service_side == "right":
            bounce = (SPEC.alley_width_m - 1.30, box_cy)
        else:
            bounce = (SPEC.doubles_width_m - SPEC.alley_width_m + 1.30, box_cy)

    elif outcome == "long":
        # 1.40 m beyond the far service line (clearly long)
        bounce = (box_cx, y_min - 1.40)

    else:
        raise ValueError(f"Unknown serve outcome: {outcome}")

    start_m = (
        SPEC.center_x_m + _side_sign(service_side) * 0.90,
        SPEC.length_m - 0.45,
    )

    f_contact = start_frame + SERVE_CONTACT_FRAME
    f_bounce = start_frame + SERVE_BOUNCE_FRAME

    net_touch_frame = None
    if outcome == "let":
        t_net = (start_m[1] - SPEC.net_y_m) / (start_m[1] - bounce[1])
        net_touch_frame = f_contact + int(round(t_net * SERVE_FLIGHT_FRAMES))

    return {
        "f_serve_start": start_frame,
        "f_toss_start": start_frame + SERVE_TOSS_FRAME,
        "f_contact": f_contact,
        "f_start": f_contact,
        "f_bounce": f_bounce,
        "f_end": start_frame + SERVE_END_FRAME,
        "start_m": start_m,
        "bounce_m": bounce,
        "end_m": (bounce[0], bounce[1] - 1.0),
        "start_z_m": _SERVE_START_Z_M,
        "peak_z_m": _SERVE_PEAK_Z_M,
        "rebound_z_m": 0.80,
        "hitter_id": 1,
        "is_serve": True,
        "service_side": service_side,
        "serve_outcome": outcome,
        "net_touch_frame": net_touch_frame,
        "foot_fault": bool(foot_fault),
        "foot_fault_frame": None,
    }


def _classify_serve(segment: dict) -> dict:
    x, y = segment["bounce_m"]
    side = segment["service_side"]

    target_mode = "service_far_left" if side == "right" else "service_far_right"
    wrong_mode = "service_far_right" if side == "right" else "service_far_left"

    target_ev = evaluate_court_point(x, y, mode=target_mode)
    wrong_ev = evaluate_court_point(x, y, mode=wrong_mode)

    outcome = segment["serve_outcome"]

    if outcome == "let":
        is_legal = bool(target_ev["is_in"])
        call = "LET" if is_legal else "FAULT"
    elif target_ev["is_in"]:
        is_legal = True
        call = "IN"
    elif wrong_ev["is_in"]:
        is_legal = False
        call = "WRONG_SERVICE_BOX"
    else:
        is_legal = False
        call = "OUT"

    return {
        "event_type": "serve_landing",
        "serve_idx": segment.get("serve_idx"),
        "serve_outcome": outcome,
        "service_side": side,
        "target_service_box": target_mode,
        "call": call,
        "is_in": bool(target_ev["is_in"]),
        "is_legal_serve": is_legal,
        "is_service_fault": not is_legal and outcome != "let",
        "is_let": outcome == "let",
        "net_touch_frame": segment.get("net_touch_frame"),
        "bounce_frame": int(segment["f_bounce"]),
        "bounce_x_m": round(float(x), 3),
        "bounce_y_m": round(float(y), 3),
        "signed_margin_cm": target_ev["signed_margin_cm"],
        "closest_line": target_ev["closest_line"],
        "in_doubt_zone": target_ev["in_doubt_zone"],
    }


def generate_synthetic_clay_rally(
    video_path: str | Path,
    gt_json_path: str | Path | None = None,
    calib_json_path: str | Path | None = None,
    width: int = 1280,
    height: int = 720,
    fps: float = 60.0,
    line_condition: Literal["fresh", "worn", "wiped"] = "worn",
    serve_side: Literal["right", "left"] = "right",
    serve_outcome: ServeOutcome = "legal",
    foot_fault: bool = False,
    serve_sequence: Optional[List[Dict[str, object]]] = None,
    include_rally: bool = True,
    reset_gap_frames: int = 40,
) -> Dict[str, object]:
    """
    Generates a flowing clay-court video that already contains:
      - legal serves
      - service faults (wrong box, long, wide) with clearly visible out landings
      - foot faults
      - combined foot + service faults
    all in one continuous clip. No need to pass a sequence.
    """
    out_video = Path(video_path)
    out_video.parent.mkdir(parents=True, exist_ok=True)

    calibrator = CourtCalibrator.from_default_camera_geometry(width=width, height=height)
    if calib_json_path is not None:
        calibrator.save(calib_json_path)

    base_bg = _build_clay_background(width, height, calibrator, line_condition=line_condition)

    # ------------------------------------------------------------------
    # Built-in flowing sequence (legal + faults mixed)
    # ------------------------------------------------------------------
    if serve_sequence is None:
        serve_scenarios = [
            # 1. Clean legal
            {"service_side": "right", "outcome": "legal",             "foot_fault": False},
            # 2. Service fault – wrong box
            {"service_side": "right", "outcome": "wrong_service_box", "foot_fault": False},
            # 3. Foot fault only (ball still in)
            {"service_side": "right", "outcome": "legal",             "foot_fault": True},
            # 4. Combined: foot fault + long fault
            {"service_side": "left",  "outcome": "long",              "foot_fault": True},
            # 5. Another service fault – wide
            {"service_side": "left",  "outcome": "wide",              "foot_fault": False},
            # 6. Final clean legal → allows rally to start
            {"service_side": "right", "outcome": "legal",             "foot_fault": False},
        ]
    else:
        serve_scenarios = serve_sequence

    serve_segments: List[Dict[str, object]] = []
    serve_events: List[Dict[str, object]] = []
    next_frame = 0

    for i, sc in enumerate(serve_scenarios):
        side = str(sc.get("service_side", "right"))
        outcome = sc.get("outcome", "legal")
        do_foot_fault = bool(sc.get("foot_fault", False))

        serve = _make_serve_segment(
            service_side=side,
            outcome=outcome,
            start_frame=next_frame,
            foot_fault=do_foot_fault,
        )
        serve["serve_idx"] = len(serve_segments)
        serve_segments.append(serve)
        serve_events.append(_classify_serve(serve))
        next_frame = int(serve["f_end"]) + 1

        if outcome == "let":
            next_frame += SERVE_RESET_GAP_FRAMES
            replay = _make_serve_segment(
                service_side=side,
                outcome="legal",
                start_frame=next_frame,
                foot_fault=False,
            )
            replay["serve_idx"] = len(serve_segments)
            serve_segments.append(replay)
            serve_events.append({**_classify_serve(replay), "is_let_replay": True})
            next_frame = int(replay["f_end"]) + 1

        if i < len(serve_scenarios) - 1:
            next_frame += reset_gap_frames

    rally_start = next_frame
    rally_segments: List[Dict[str, object]] = []

    last_serve = serve_segments[-1]
    can_rally = (
        include_rally
        and (
            last_serve["serve_outcome"] == "legal"
            or last_serve.get("is_let_replay", False)
        )
    )

    if can_rally:
        previous = last_serve

        def make_groundstroke(
            hitter_id: int,
            start_xy: Tuple[float, float],
            bounce_xy: Tuple[float, float],
            f_start: int,
            flight_frames: int = 42,
            rebound_frames: int = 16,
        ) -> Dict[str, object]:
            f_bounce = f_start + flight_frames
            f_end = f_bounce + rebound_frames

            bx, by = bounce_xy
            if hitter_id == 1:
                end_xy = (bx + (bx - start_xy[0]) * 0.2, max(1.5, by - 2.5))
            else:
                end_xy = (bx + (bx - start_xy[0]) * 0.2, min(SPEC.length_m - 1.5, by + 2.5))

            return {
                "f_start": f_start,
                "f_contact": f_start,
                "f_bounce": f_bounce,
                "f_end": f_end,
                "start_m": start_xy,
                "bounce_m": bounce_xy,
                "end_m": end_xy,
                "start_z_m": 0.90,
                "peak_z_m": 1.85,
                "rebound_z_m": 0.75,
                "hitter_id": hitter_id,
                "is_serve": False,
            }

        f = int(previous["f_end"]) + 1

        # 1. P2 return
        start2 = previous["end_m"]
        start2 = (float(start2[0]), max(-0.4, float(start2[1]) - 0.3))
        bounce2 = (SPEC.center_x_m + 1.9, SPEC.length_m - 3.8)
        seg2 = make_groundstroke(2, start2, bounce2, f, flight_frames=40, rebound_frames=14)
        rally_segments.append(seg2)
        f = int(seg2["f_end"]) + 1

        # 2. P1 cross-court
        start1 = seg2["end_m"]
        start1 = (float(start1[0]), min(SPEC.length_m + 0.4, float(start1[1]) + 0.3))
        bounce1 = (SPEC.center_x_m - 2.3, 4.2)
        seg1 = make_groundstroke(1, start1, bounce1, f)
        rally_segments.append(seg1)
        f = int(seg1["f_end"]) + 1

        # 3. P2 down-the-line
        start2b = seg1["end_m"]
        start2b = (float(start2b[0]), max(-0.4, float(start2b[1]) - 0.3))
        bounce2b = (SPEC.center_x_m + 2.5, SPEC.length_m - 2.9)
        seg2b = make_groundstroke(2, start2b, bounce2b, f)
        rally_segments.append(seg2b)
        f = int(seg2b["f_end"]) + 1

        # 4. P1 finishing shot
        start1b = seg2b["end_m"]
        start1b = (float(start1b[0]), min(SPEC.length_m + 0.4, float(start1b[1]) + 0.3))
        bounce1b = (SPEC.center_x_m - 1.1, 6.8)
        seg1b = make_groundstroke(1, start1b, bounce1b, f, flight_frames=34, rebound_frames=12)
        rally_segments.append(seg1b)

    all_segments = [*serve_segments, *rally_segments]

    last_end = max(int(seg["f_end"]) for seg in all_segments) if all_segments else 0
    total_frames = last_end + 15
    if include_rally and can_rally:
        total_frames = max(320, total_frames)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_video), fourcc, fps, (width, height))

    gt_frames: List[Dict[str, object]] = []
    gt_bounces: List[Dict[str, object]] = []

    for seg in all_segments:
        bx, by = seg["bounce_m"]
        half = "far" if by < SPEC.net_y_m else "near"

        if seg.get("is_serve"):
            ev = serve_events[int(seg["serve_idx"])]
        else:
            ev = evaluate_court_point(bx, by, mode="singles", target_half=half)

        b_uv = calibrator.point_court_to_image(bx, by)

        gt_bounces.append({
            "frame_idx": int(seg["f_bounce"]),
            "u": round(float(b_uv[0]), 2),
            "v": round(float(b_uv[1]), 2),
            "x_m": round(float(bx), 3),
            "y_m": round(float(by), 3),
            "call": ev["call"],
            "is_in": bool(ev["is_in"]),
            "signed_margin_cm": ev.get("signed_margin_cm"),
            "in_doubt_zone": ev.get("in_doubt_zone", False),
            "closest_line": ev.get("closest_line"),
            "court_half": half,
            "is_serve": bool(seg.get("is_serve", False)),
            "serve_idx": seg.get("serve_idx"),
            "serve_outcome": seg.get("serve_outcome"),
        })

    for f in range(total_frames):
        frame = base_bg.copy()

        (p1_left_m, p1_right_m), (p2_left_m, p2_right_m) = _interpolate_players(
            f, serve_segments, rally_start, rally_segments
        )

        p1_left_px = calibrator.point_court_to_image(*p1_left_m)
        p1_right_px = calibrator.point_court_to_image(*p1_right_m)
        p2_left_px = calibrator.point_court_to_image(*p2_left_m)
        p2_right_px = calibrator.point_court_to_image(*p2_right_m)

        p1_mid_m = (
            0.5 * (p1_left_m[0] + p1_right_m[0]),
            0.5 * (p1_left_m[1] + p1_right_m[1]),
        )
        p2_mid_m = (
            0.5 * (p2_left_m[0] + p2_right_m[0]),
            0.5 * (p2_left_m[1] + p2_right_m[1]),
        )

        active_serve = _serve_window(f, serve_segments)
        in_serve = active_serve is not None
        pre_contact = in_serve and f < int(active_serve["f_contact"])

        if (
            pre_contact
            and active_serve["foot_fault_frame"] is None
            and min(p1_left_m[1], p1_right_m[1]) <= SPEC.length_m
        ):
            active_serve["foot_fault_frame"] = f

        _draw_player_sprite(
            frame,
            left_foot_px=p2_left_px,
            right_foot_px=p2_right_px,
            scale=0.62,
            kit_bgr=(215, 95, 165),
            shorts_bgr=(45, 35, 55),
        )

        ball_info = _interpolate_ball_3d(f, all_segments, calibrator)

        # Longer + stronger clay dust so bounce location is easy to see
        for gb in gt_bounces:
            dt_b = f - int(gb["frame_idx"])
            if 0 <= dt_b <= 22:
                du, dv = int(round(float(gb["u"]))), int(round(float(gb["v"])))
                dust_layer = frame.copy()
                r_dust = int(6 + dt_b * 1.25)
                cv2.ellipse(
                    dust_layer,
                    (du, dv),
                    (r_dust, max(3, r_dust // 2)),
                    0, 0, 360,
                    (145, 175, 215),
                    -1,
                    cv2.LINE_AA,
                )
                alpha_d = max(0.06, 0.45 * (1.0 - dt_b / 23.0))
                frame = cv2.addWeighted(dust_layer, alpha_d, frame, 1.0 - alpha_d, 0)

        frame_gt: Dict[str, object] = {
            "frame_idx": f,
            "ball_u": None,
            "ball_v": None,
            "ball_x_m": None,
            "ball_y_m": None,
            "p1_left_foot_xy_m": [round(p1_left_m[0], 3), round(p1_left_m[1], 3)],
            "p1_right_foot_xy_m": [round(p1_right_m[0], 3), round(p1_right_m[1], 3)],
            "p2_left_foot_xy_m": [round(p2_left_m[0], 3), round(p2_left_m[1], 3)],
            "p2_right_foot_xy_m": [round(p2_right_m[0], 3), round(p2_right_m[1], 3)],
            "p1_xy_m": [round(p1_mid_m[0], 3), round(p1_mid_m[1], 3)],
            "p2_xy_m": [round(p2_mid_m[0], 3), round(p2_mid_m[1], 3)],
            "server_id": 1 if in_serve else None,
            "serving_end": "near" if in_serve else None,
            "service_side": active_serve["service_side"] if in_serve else None,
            "service_motion_active": in_serve,
            "pre_contact": bool(pre_contact),
            "serve_idx": active_serve["serve_idx"] if in_serve else None,
        }

        if ball_info is not None:
            bu, bv, shadow_u, shadow_v, radius_px, bx_m, by_m = ball_info
            cv2.ellipse(
                frame,
                (int(round(shadow_u)), int(round(shadow_v))),
                (max(3, int(radius_px)), max(2, int(radius_px * 0.5))),
                0, 0, 360,
                (45, 65, 115),
                -1,
                cv2.LINE_AA,
            )
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
            frame_gt.update(
                ball_u=round(bu, 2),
                ball_v=round(bv, 2),
                ball_x_m=round(bx_m, 3),
                ball_y_m=round(by_m, 3),
            )

        gt_frames.append(frame_gt)

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

    for seg, ev in zip(serve_segments, serve_events):
        ev["foot_fault_frame"] = seg["foot_fault_frame"]
        ev["is_foot_fault"] = seg["foot_fault_frame"] is not None
        ev["contact_frame"] = int(seg["f_contact"])

    first = serve_segments[0]
    gt_payload = {
        "video_path": str(out_video),
        "width": width,
        "height": height,
        "fps": fps,
        "line_condition": line_condition,
        "anchors_px": {k: list(v) for k, v in calibrator.anchors_px.items()},
        "bounces": gt_bounces,
        "frames": gt_frames,
        "serve": {
            "server_id": 1,
            "serving_end": "near",
            "service_side": first["service_side"],
            "motion_start_frame": int(first["f_serve_start"]),
            "motion_end_frame": int(first["f_end"]),
            "contact_frame": int(first["f_contact"]),
            "fault_start_frame": first["foot_fault_frame"],
            "is_foot_fault": first["foot_fault_frame"] is not None,
            "serve_events": serve_events,
            "serve_segments": serve_segments,
            "rally_start_frame": rally_start,
            "rally_segment_count": len(rally_segments),
            "total_segment_count": len(all_segments),
        },
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
    bg = np.full((height, width, 3), (72, 96, 158), dtype=np.uint8)

    horizon_y = int(height * 0.14)
    bg[:horizon_y, :] = (52, 78, 62)

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
    cv2.fillPoly(bg, [court_poly_px], (68, 108, 188))

    noise = rng.integers(-9, 10, size=(height, width, 3), dtype=np.int16)
    bg = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)

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
            wear_mask = rng.uniform(0.0, 1.0, size=(height // 8, width // 8)).astype(np.float32)
            wear_mask = cv2.resize(wear_mask, (width, height), interpolation=cv2.INTER_LINEAR)
            alpha = (wear_mask > 0.55).astype(np.float32) * 0.35
            bg = (line_layer * alpha[..., None] + bg * (1.0 - alpha[..., None])).astype(np.uint8)

    net_pts = calibrator.court_to_image([(0.0, SPEC.net_y_m), (SPEC.doubles_width_m, SPEC.net_y_m)])
    nl = (int(round(net_pts[0, 0])), int(round(net_pts[0, 1])))
    nr = (int(round(net_pts[1, 0])), int(round(net_pts[1, 1])))
    cv2.line(bg, (nl[0], nl[1] - 26), (nr[0], nr[1] - 26), (235, 235, 235), 2, cv2.LINE_AA)
    cv2.line(bg, nl, (nl[0], nl[1] - 28), (50, 55, 60), 4, cv2.LINE_AA)
    cv2.line(bg, nr, (nr[0], nr[1] - 28), (50, 55, 60), 4, cv2.LINE_AA)

    for k, (u, v) in calibrator.anchors_px.items():
        cv2.circle(bg, (int(round(u)), int(round(v))), 4, (235, 245, 255), -1, cv2.LINE_AA)

    return bg


def _split_feet(mid_xy_m: Tuple[float, float]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    x, y = mid_xy_m
    left = (x - _FOOT_HALF_WIDTH_M, y)
    right = (x + _FOOT_HALF_WIDTH_M, y)
    return left, right


def _serve_window(
    frame_idx: int,
    serve_segments: List[Dict[str, object]],
) -> Optional[Dict[str, object]]:
    for seg in serve_segments:
        if int(seg["f_serve_start"]) <= frame_idx <= int(seg["f_end"]):
            return seg
    return None


def _serve_p1_feet(
    local: int,
    service_side: str,
    foot_fault: bool,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    mid_x = _serve_stance_mid_x(service_side)
    c = SERVE_CONTACT_FRAME
    f0 = _SERVE_FAULT_START

    if foot_fault:
        r_t = [0, f0 - 8, f0, c + 10, SERVE_END_FRAME]
        r_y = [_SERVE_STANCE_Y_M, _SERVE_STANCE_Y_M, _SERVE_FAULT_FOOT_Y_M,
               _SERVE_STEP_IN_Y_M, _SERVE_STEP_IN_Y_M]
    else:
        r_t = [0, c, c + 10, SERVE_END_FRAME]
        r_y = [_SERVE_STANCE_Y_M, _SERVE_STANCE_Y_M, _SERVE_STEP_IN_Y_M, _SERVE_STEP_IN_Y_M]
    right_y = float(np.interp(local, r_t, r_y))

    left_y = float(np.interp(
        local,
        [0, c, c + 12, SERVE_END_FRAME],
        [24.25, 24.25, _SERVE_STEP_IN_Y_M, _SERVE_STEP_IN_Y_M],
    ))

    left = (mid_x - _FOOT_HALF_WIDTH_M, left_y)
    right = (mid_x + _FOOT_HALF_WIDTH_M, right_y)
    return left, right


def _serve_feet_at(seg: Dict[str, object], frame_idx: int):
    local = frame_idx - int(seg["f_serve_start"])
    return _serve_p1_feet(local, str(seg["service_side"]), bool(seg["foot_fault"]))


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _interpolate_players(
    frame_idx: int,
    serve_segments: List[Dict[str, object]],
    rally_start: int,
    rally_segments: Optional[List[Dict[str, object]]] = None,
) -> Tuple[
    Tuple[Tuple[float, float], Tuple[float, float]],
    Tuple[Tuple[float, float], Tuple[float, float]],
]:
    rally_segments = rally_segments or []

    active = _serve_window(frame_idx, serve_segments)
    if active is not None:
        p1_left, p1_right = _serve_feet_at(active, frame_idx)
    else:
        p1_keys = [(rally_start, (6.40, SPEC.length_m + 0.55))]

        for i, seg in enumerate(rally_segments):
            if int(seg["hitter_id"]) == 1:
                arrival_frame = int(seg["f_contact"]) - 10
                x, y = seg["start_m"]
                plant_y = max(y, SPEC.length_m + 0.15)
                p1_keys.append((arrival_frame, (float(x), plant_y)))
                p1_keys.append((int(seg["f_contact"]), (float(x), float(y))))

        p1_keys.sort(key=lambda item: item[0])
        p1_left, p1_right = _split_feet(_interp_path(frame_idx, p1_keys))

    p2_keys = [(0, (4.50, -0.55))]

    for seg in rally_segments:
        if int(seg["hitter_id"]) == 2:
            arrival_frame = int(seg["f_contact"]) - 10
            x, y = seg["start_m"]
            plant_y = min(y, -0.15)
            p2_keys.append((arrival_frame, (float(x), plant_y)))
            p2_keys.append((int(seg["f_contact"]), (float(x), float(y))))

    p2_keys.sort(key=lambda item: item[0])
    p2_left, p2_right = _split_feet(_interp_path(frame_idx, p2_keys))

    return (p1_left, p1_right), (p2_left, p2_right)


def _interp_path(
    frame_idx: int,
    keys: List[Tuple[int, Tuple[float, float]]],
) -> Tuple[float, float]:
    if not keys:
        return (0.0, 0.0)
    if frame_idx <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys) - 1):
        f0, p0 = keys[i]
        f1, p1 = keys[i + 1]
        if f0 <= frame_idx <= f1:
            s = _smoothstep((frame_idx - f0) / max(1, f1 - f0))
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
        f_first = int(seg.get("f_toss_start", f_start))
        if not (f_first <= frame_idx <= f_end):
            continue

        s_m = seg["start_m"]
        b_m = seg["bounce_m"]
        e_m = seg["end_m"]
        peak_z = float(seg["peak_z_m"])
        reb_z = float(seg["rebound_z_m"])
        z0 = float(seg.get("start_z_m", 0.95))

        if frame_idx < f_start:
            u = (frame_idx - f_first) / max(1, f_start - f_first)
            xm, ym = s_m[0], s_m[1]
            zm = 1.0 + (z0 - 1.0) * float(np.sin(0.5 * np.pi * u))
        elif frame_idx <= f_bounce:
            t = (frame_idx - f_start) / max(1, f_bounce - f_start)
            xm = s_m[0] + t * (b_m[0] - s_m[0])
            ym = s_m[1] + t * (b_m[1] - s_m[1])
            zm = max(0.0, 4.0 * peak_z * t * (1.0 - t) + z0 * (1.0 - t) * (1.0 - t))
        else:
            t = (frame_idx - f_bounce) / max(1, f_end - f_bounce)
            xm = b_m[0] + t * (e_m[0] - b_m[0])
            ym = b_m[1] + t * (e_m[1] - b_m[1])
            zm = max(0.0, reb_z * np.sin(0.75 * np.pi * t))

        shadow_u, shadow_v = calibrator.point_court_to_image(xm, ym)
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
    lu, lv = float(left_foot_px[0]), float(left_foot_px[1])
    ru, rv = float(right_foot_px[0]), float(right_foot_px[1])

    u = int(round(0.5 * (lu + ru)))
    v = int(round(0.5 * (lv + rv)))

    h_tot = int(round(76 * scale))
    w_torso = int(round(20 * scale))
    leg_h = int(h_tot * 0.42)

    cv2.ellipse(
        frame,
        (u, v),
        (int(16 * scale), int(6 * scale)),
        0, 0, 360,
        (42, 62, 105),
        -1,
        cv2.LINE_AA,
    )

    cv2.line(
        frame,
        (int(round(lu)), int(round(lv))),
        (u - int(4 * scale), v - leg_h),
        (95, 120, 165),
        max(2, int(4 * scale)),
        cv2.LINE_AA,
    )
    cv2.line(
        frame,
        (int(round(ru)), int(round(rv))),
        (u + int(4 * scale), v - leg_h),
        (95, 120, 165),
        max(2, int(4 * scale)),
        cv2.LINE_AA,
    )

    shorts_top = v - int(h_tot * 0.54)
    cv2.rectangle(
        frame,
        (u - w_torso // 2, shorts_top),
        (u + w_torso // 2, v - int(h_tot * 0.36)),
        shorts_bgr,
        -1,
    )

    torso_top = v - int(h_tot * 0.84)
    cv2.rectangle(
        frame,
        (u - w_torso // 2, torso_top),
        (u + w_torso // 2, shorts_top),
        kit_bgr,
        -1,
    )

    head_r = max(4, int(round(8 * scale)))
    cv2.circle(
        frame,
        (u, torso_top - head_r),
        head_r,
        (95, 120, 165),
        -1,
        cv2.LINE_AA,
    )