#!/usr/bin/env python3
"""Calibrate court homography from anchors or interactive clicks (matches README Section 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calibration.court_geometry import DEFAULT_6_ANCHOR_NAMES
from src.calibration.homography import CourtCalibrator
from src.calibration.virtual_court import VirtualCourtRenderer


def main() -> None:
    parser = argparse.ArgumentParser(description="CLEAR: Calibrate court homography from anchor points.")
    parser.add_argument("--video", type=str, required=False, default="data/demo/ucu_clay_rally.mp4", help="Input video path")
    parser.add_argument("--out", type=str, required=True, help="Output calibration JSON path (e.g. calib/session.json)")
    parser.add_argument("--mode", choices=["anchors", "painted_b2", "interactive"], default="anchors")
    parser.add_argument("--preview", type=str, default=None, help="Optional path to save virtual court preview PNG")
    args = parser.parse_args()

    video_path = Path(args.video)
    width, height = 1280, 720
    frame = None

    if video_path.exists():
        cap = cv2.VideoCapture(str(video_path))
        ret, frm = cap.read()
        cap.release()
        if ret and frm is not None:
            frame = frm
            height, width = frame.shape[:2]

    if args.mode == "painted_b2" and frame is not None:
        calibrator = CourtCalibrator.from_painted_lines_baseline(frame)
    elif args.mode == "interactive" and frame is not None:
        clicked = {}
        disp = frame.copy()
        idx = 0

        def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
            nonlocal idx, disp
            if event == cv2.EVENT_LBUTTONDOWN and idx < len(DEFAULT_6_ANCHOR_NAMES):
                name = DEFAULT_6_ANCHOR_NAMES[idx]
                clicked[name] = (float(x), float(y))
                cv2.circle(disp, (x, y), 6, (0, 215, 255), -1)
                cv2.putText(disp, name, (x + 8, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                idx += 1

        cv2.namedWindow("Tap 4-6 Court Anchors (Press Q/Enter when done)")
        cv2.setMouseCallback("Tap 4-6 Court Anchors (Press Q/Enter when done)", on_mouse)
        while True:
            cv2.imshow("Tap 4-6 Court Anchors (Press Q/Enter when done)", disp)
            key = cv2.waitKey(20) & 0xFF
            if key in (13, 27, ord("q")) or idx >= len(DEFAULT_6_ANCHOR_NAMES):
                break
        cv2.destroyAllWindows()
        calibrator = (
            CourtCalibrator(anchors_px=clicked)
            if len(clicked) >= 4
            else CourtCalibrator.from_default_camera_geometry(width, height)
        )
    else:
        calibrator = CourtCalibrator.from_default_camera_geometry(width=width, height=height)

    calibrator.save(args.out)

    if args.preview and frame is not None:
        renderer = VirtualCourtRenderer(calibrator=calibrator)
        prev = renderer.draw(frame, draw_doubt_zone=True, draw_anchors=True)
        Path(args.preview).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(args.preview, prev)

    print(
        json.dumps(
            {
                "status": "calibrated",
                "method": calibrator.method,
                "out": args.out,
                "reproj_error_px": round(calibrator.reproj_error_px, 3),
                "reproj_error_cm": round(calibrator.reproj_error_cm, 3),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
