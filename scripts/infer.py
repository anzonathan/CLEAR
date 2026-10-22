#!/usr/bin/env python3
"""Run CLEAR inference on a rally video (matches README Section 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calibration.homography import CourtCalibrator
from src.data.synthetic_rally import generate_synthetic_clay_rally
from src.pipeline import ClearPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="CLEAR: Run ball/player tracking and automated line calling.")
    parser.add_argument(
        "--video",
        type=str,
        default="data/demo/ucu_clay_rally.mp4",
        help="Path to input rally video (auto-generates synthetic clay rally if missing)",
    )
    parser.add_argument(
        "--calib",
        type=str,
        default="calib/session.json",
        help="Path to calibration JSON file",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results/rally1",
        help="Output directory for annotated video, bounces.json, and court chart",
    )
    parser.add_argument(
        "--court-mode",
        choices=["singles", "doubles"],
        default="singles",
        help="Active court boundaries (singles or doubles)",
    )
    parser.add_argument(
        "--detector",
        choices=["hybrid", "yolo", "classical"],
        default="hybrid",
        help="Detection mode",
    )
    args = parser.parse_args()

    video_path = Path(args.video)
    calib_path = Path(args.calib)

    if not video_path.exists():
        print(f"[CLEAR] Generating synthetic clay-court demo rally at {video_path} ...")
        generate_synthetic_clay_rally(
            video_path=video_path,
            gt_json_path=video_path.with_name(video_path.stem + "_gt.json"),
            calib_json_path=calib_path,
        )

    if calib_path.exists():
        calibrator = CourtCalibrator.load(calib_path)
    else:
        calibrator = CourtCalibrator.from_default_camera_geometry()
        calibrator.save(calib_path)

    pipeline = ClearPipeline(
        calibrator=calibrator,
        court_mode=args.court_mode,  # type: ignore[arg-type]
        detector_mode=args.detector,  # type: ignore[arg-type]
    )
    report = pipeline.run_video(video_path=video_path, out_dir=args.out)

    print(
        json.dumps(
            {
                "annotated_video": report["annotated_video"],
                "ball_coverage_pct": report["ball_tracking"]["coverage_pct"],
                "max_ball_speed_kmh": report["ball_tracking"]["max_speed_kmh"],
                "total_bounces": report["line_calling"]["total_bounces"],
                "bounces": report["line_calling"]["bounces"],
                "score": report["score"]["score_line"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
