"""Optional court-segmentation hook for the field console.

A segmentation model is only used when weights are supplied via
``CLEAR_COURT_SEG_WEIGHTS``. No weights are bundled: a court-segmentation model
must be trained and labelled first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .auto_court import order_court_quad, _plausible_quad


def detect_court_with_segmentation(
    frame_bgr: np.ndarray,
    weights_path: str | Path,
) -> tuple[Optional[list[tuple[float, float]]], float, str]:
    path = Path(weights_path)
    if not path.exists():
        return None, 0.0, "Court segmentation weights not configured."
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on deployment extras
        return None, 0.0, f"Ultralytics unavailable: {exc}"

    try:
        model = YOLO(str(path))
        results = model.predict(frame_bgr, verbose=False, conf=0.25)
        if not results:
            return None, 0.0, "Segmentation model returned no result."
        result = results[0]
        if result.masks is None or len(result.masks.data) == 0:
            return None, 0.0, "No court mask generated."

        mask = result.masks.data[0].detach().cpu().numpy().astype(np.uint8)
        mask = cv2.resize(mask, (frame_bgr.shape[1], frame_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0.0, "Court mask had no contour."
        contour = max(contours, key=cv2.contourArea)
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.03 * perimeter, True)
        quad = approx.reshape(-1, 2).astype(np.float64) if len(approx) == 4 else None
        if quad is None:
            rect = cv2.minAreaRect(hull)
            quad = cv2.boxPoints(rect)
        ordered = order_court_quad(quad)
        if not _plausible_quad(np.asarray(ordered), frame_bgr.shape[1], frame_bgr.shape[0]):
            return None, 0.0, "Segmentation outline was not court-shaped."
        return ordered, 0.8, "Court mask detected. Confirm before relying on it."
    except Exception as exc:
        return None, 0.0, f"Segmentation failed: {exc}"
