"""Frame orientation helpers: every video CLEAR processes or records is landscape."""

from __future__ import annotations

import os

import cv2
import numpy as np

# Direction used to turn a portrait frame into landscape: "cw" (default) or "ccw".
_ROTATIONS = {
    "cw": cv2.ROTATE_90_CLOCKWISE,
    "ccw": cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _rotation_code() -> int:
    direction = os.getenv("CLEAR_LANDSCAPE_ROTATION", "cw").strip().lower()
    return _ROTATIONS.get(direction, cv2.ROTATE_90_CLOCKWISE)


def is_portrait(width: int, height: int) -> bool:
    return height > width


def landscape_size(width: int, height: int) -> tuple[int, int]:
    """(width, height) a frame of this size will have after ensure_landscape."""
    return (height, width) if is_portrait(width, height) else (width, height)


def ensure_landscape(frame: np.ndarray) -> np.ndarray:
    """Rotate a portrait frame 90 degrees so it is landscape; landscape frames pass through."""
    h, w = frame.shape[:2]
    if not is_portrait(w, h):
        return frame
    return cv2.rotate(frame, _rotation_code())
