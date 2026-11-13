"""Standard ITF tennis court geometry in metres and exact line-distance calculation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple
import numpy as np


@dataclass(frozen=True)
class ITFCourtSpec:
    """ITF regulation tennis court dimensions in metres.

    Coordinate system (top-down):
      - Origin (0.0, 0.0) is Far-Left Doubles Corner.
      - X axis [0.0 .. 10.97]: Left Doubles Sideline -> Right Doubles Sideline.
      - Y axis [0.0 .. 23.77]: Far Baseline -> Near Baseline.
    """

    length_m: float = 23.77
    doubles_width_m: float = 10.97
    singles_width_m: float = 8.23
    alley_width_m: float = 1.37  # (10.97 - 8.23) / 2
    net_y_m: float = 11.885  # 23.77 / 2
    service_offset_m: float = 6.40
    far_service_y_m: float = 5.485  # 11.885 - 6.40
    near_service_y_m: float = 18.285  # 11.885 + 6.40
    center_x_m: float = 5.485  # 10.97 / 2
    center_mark_len_m: float = 0.15
    line_width_m: float = 0.05


SPEC = ITFCourtSpec()

# Physical anchor coordinates in court metres (X, Y)
ANCHOR_COORDS_M: Dict[str, Tuple[float, float]] = {
    # Primary 4 corner pegs (doubles corners)
    "far_left_doubles": (0.0, 0.0),
    "far_right_doubles": (SPEC.doubles_width_m, 0.0),
    "near_right_doubles": (SPEC.doubles_width_m, SPEC.length_m),
    "near_left_doubles": (0.0, SPEC.length_m),
    # Net line sideline intersections / posts
    "net_left_sideline": (0.0, SPEC.net_y_m),
    "net_right_sideline": (SPEC.doubles_width_m, SPEC.net_y_m),
    # Singles corners
    "far_left_singles": (SPEC.alley_width_m, 0.0),
    "far_right_singles": (SPEC.doubles_width_m - SPEC.alley_width_m, 0.0),
    "near_right_singles": (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.length_m),
    "near_left_singles": (SPEC.alley_width_m, SPEC.length_m),
    # Service line intersections
    "far_service_left": (SPEC.alley_width_m, SPEC.far_service_y_m),
    "far_service_center": (SPEC.center_x_m, SPEC.far_service_y_m),
    "far_service_right": (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.far_service_y_m),
    "near_service_left": (SPEC.alley_width_m, SPEC.near_service_y_m),
    "near_service_center": (SPEC.center_x_m, SPEC.near_service_y_m),
    "near_service_right": (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.near_service_y_m),
    # Net center
    "net_center": (SPEC.center_x_m, SPEC.net_y_m),
}

DEFAULT_4_ANCHOR_NAMES: List[str] = [
    "far_left_doubles",
    "far_right_doubles",
    "near_right_doubles",
    "near_left_doubles",
]

DEFAULT_6_ANCHOR_NAMES: List[str] = [
    "far_left_doubles",
    "far_right_doubles",
    "net_right_sideline",
    "near_right_doubles",
    "near_left_doubles",
    "net_left_sideline",
]

# Named court line segments: (name, (x1, y1), (x2, y2), category)
COURT_LINES_M: List[Tuple[str, Tuple[float, float], Tuple[float, float], str]] = [
    ("far_baseline", (0.0, 0.0), (SPEC.doubles_width_m, 0.0), "baseline"),
    ("near_baseline", (0.0, SPEC.length_m), (SPEC.doubles_width_m, SPEC.length_m), "baseline"),
    ("left_doubles_sideline", (0.0, 0.0), (0.0, SPEC.length_m), "doubles"),
    (
        "right_doubles_sideline",
        (SPEC.doubles_width_m, 0.0),
        (SPEC.doubles_width_m, SPEC.length_m),
        "doubles",
    ),
    (
        "left_singles_sideline",
        (SPEC.alley_width_m, 0.0),
        (SPEC.alley_width_m, SPEC.length_m),
        "singles",
    ),
    (
        "right_singles_sideline",
        (SPEC.doubles_width_m - SPEC.alley_width_m, 0.0),
        (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.length_m),
        "singles",
    ),
    (
        "far_service_line",
        (SPEC.alley_width_m, SPEC.far_service_y_m),
        (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.far_service_y_m),
        "service",
    ),
    (
        "near_service_line",
        (SPEC.alley_width_m, SPEC.near_service_y_m),
        (SPEC.doubles_width_m - SPEC.alley_width_m, SPEC.near_service_y_m),
        "service",
    ),
    (
        "center_service_line",
        (SPEC.center_x_m, SPEC.far_service_y_m),
        (SPEC.center_x_m, SPEC.near_service_y_m),
        "service",
    ),
    (
        "far_center_mark",
        (SPEC.center_x_m, 0.0),
        (SPEC.center_x_m, SPEC.center_mark_len_m),
        "mark",
    ),
    (
        "near_center_mark",
        (SPEC.center_x_m, SPEC.length_m - SPEC.center_mark_len_m),
        (SPEC.center_x_m, SPEC.length_m),
        "mark",
    ),
    ("net_line", (0.0, SPEC.net_y_m), (SPEC.doubles_width_m, SPEC.net_y_m), "net"),
]


CourtMode = Literal[
    "singles",
    "doubles",
    "service_far_left",
    "service_far_right",
    "service_near_left",
    "service_near_right",
]


def get_active_bounds(
    mode: CourtMode = "singles",
    target_half: Literal["full", "far", "near"] = "full",
) -> Tuple[float, float, float, float, Dict[str, str]]:
    """Return (x_min, x_max, y_min, y_max, boundary_names) for the active court region."""
    if mode == "doubles":
        x_min, x_max = 0.0, SPEC.doubles_width_m
        left_name, right_name = "left_doubles_sideline", "right_doubles_sideline"
    elif mode == "service_far_left":
        return (
            SPEC.alley_width_m,
            SPEC.center_x_m,
            SPEC.far_service_y_m,
            SPEC.net_y_m,
            {
                "left": "left_singles_sideline",
                "right": "center_service_line",
                "top": "far_service_line",
                "bottom": "net_line",
            },
        )
    elif mode == "service_far_right":
        return (
            SPEC.center_x_m,
            SPEC.doubles_width_m - SPEC.alley_width_m,
            SPEC.far_service_y_m,
            SPEC.net_y_m,
            {
                "left": "center_service_line",
                "right": "right_singles_sideline",
                "top": "far_service_line",
                "bottom": "net_line",
            },
        )
    elif mode == "service_near_left":
        return (
            SPEC.alley_width_m,
            SPEC.center_x_m,
            SPEC.net_y_m,
            SPEC.near_service_y_m,
            {
                "left": "left_singles_sideline",
                "right": "center_service_line",
                "top": "net_line",
                "bottom": "near_service_line",
            },
        )
    elif mode == "service_near_right":
        return (
            SPEC.center_x_m,
            SPEC.doubles_width_m - SPEC.alley_width_m,
            SPEC.net_y_m,
            SPEC.near_service_y_m,
            {
                "left": "center_service_line",
                "right": "right_singles_sideline",
                "top": "net_line",
                "bottom": "near_service_line",
            },
        )
    else:
        x_min = SPEC.alley_width_m
        x_max = SPEC.doubles_width_m - SPEC.alley_width_m
        left_name, right_name = "left_singles_sideline", "right_singles_sideline"

    if target_half == "far":
        y_min, y_max = 0.0, SPEC.net_y_m
        top_name, bottom_name = "far_baseline", "net_line"
    elif target_half == "near":
        y_min, y_max = SPEC.net_y_m, SPEC.length_m
        top_name, bottom_name = "net_line", "near_baseline"
    else:
        y_min, y_max = 0.0, SPEC.length_m
        top_name, bottom_name = "far_baseline", "near_baseline"

    names = {
        "left": left_name,
        "right": right_name,
        "top": top_name,
        "bottom": bottom_name,
    }
    return x_min, x_max, y_min, y_max, names


def evaluate_court_point(
    x_m: float,
    y_m: float,
    mode: CourtMode = "singles",
    target_half: Literal["full", "far", "near"] = "full",
    ball_contact_radius_cm: float = 3.8,
    doubt_zone_cm: float = 15.0,
    reproj_uncertainty_cm: float = 3.5,
) -> Dict[str, object]:
    """Judge whether a bounce at (x_m, y_m) is IN or OUT.

    In tennis, if any part of the ball's contact patch touches the outside edge
    of a boundary line, the ball is IN.

    Returns a dict with:
      - is_in (bool)
      - call ("IN" | "OUT")
      - signed_margin_cm (float): positive = inside boundary + contact tolerance, negative = out
      - abs_margin_cm (float)
      - closest_line (str)
      - in_doubt_zone (bool): True if |margin_cm| <= doubt_zone_cm
      - confidence (float): [0.5 .. 0.99] based on margin vs uncertainty
    """
    x_min, x_max, y_min, y_max, names = get_active_bounds(mode=mode, target_half=target_half)
    half_line_m = SPEC.line_width_m * 0.5
    contact_m = (ball_contact_radius_cm / 100.0) + half_line_m

    # Signed distances to outer edges of active boundary lines (positive = inside)
    d_left_m = (x_m - x_min) + contact_m
    d_right_m = (x_max - x_m) + contact_m
    d_top_m = (y_m - y_min) + contact_m
    d_bottom_m = (y_max - y_m) + contact_m

    candidates = [
        (d_left_m, names["left"]),
        (d_right_m, names["right"]),
        (d_top_m, names["top"]),
        (d_bottom_m, names["bottom"]),
    ]

    # When target_half is "full", net line is internal, so only outer boundaries trigger OUT.
    min_dist_m, closest_line = min(candidates, key=lambda item: item[0])
    signed_margin_cm = float(min_dist_m * 100.0)
    abs_margin_cm = abs(signed_margin_cm)
    is_in = signed_margin_cm >= 0.0
    in_doubt_zone = abs_margin_cm <= doubt_zone_cm

    # Smooth sigmoid/error-function confidence from margin vs calibration uncertainty
    sigma = max(1.5, reproj_uncertainty_cm)
    z = abs_margin_cm / sigma
    conf = float(0.50 + 0.49 * np.tanh(0.65 * z))

    return {
        "x_m": round(float(x_m), 3),
        "y_m": round(float(y_m), 3),
        "is_in": bool(is_in),
        "call": "IN" if is_in else "OUT",
        "signed_margin_cm": round(signed_margin_cm, 1),
        "abs_margin_cm": round(abs_margin_cm, 1),
        "closest_line": closest_line,
        "in_doubt_zone": bool(in_doubt_zone),
        "confidence": round(conf, 3),
    }
