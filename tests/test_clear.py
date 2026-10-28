"""Unit and integration tests for CLEAR pipeline, geometry, calibration, score engine, and web app."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

from App.server import app
from src.calibration.court_geometry import SPEC, evaluate_court_point
from src.calibration.homography import CourtCalibrator
from src.calibration.virtual_court import VirtualCourtRenderer
from src.score.score_engine import TennisScoreEngine


def test_court_geometry_in_out_and_doubt_zone() -> None:
    # Center of singles court -> clearly IN
    res_in = evaluate_court_point(5.485, 18.0, mode="singles", target_half="near")
    assert res_in["is_in"] is True
    assert res_in["call"] == "IN"
    assert res_in["in_doubt_zone"] is False

    # Right singles sideline is at x = 9.60m -> ball at x = 9.59m is IN inside Doubt Zone (<15cm)
    res_doubt = evaluate_court_point(9.59, 19.65, mode="singles", target_half="near")
    assert res_doubt["is_in"] is True
    assert res_doubt["in_doubt_zone"] is True
    assert res_doubt["closest_line"] == "right_singles_sideline"

    # Doubles alley (x = 0.60m): OUT in singles, IN in doubles
    res_alley_s = evaluate_court_point(0.60, 18.0, mode="singles", target_half="near")
    res_alley_d = evaluate_court_point(0.60, 18.0, mode="doubles", target_half="near")
    assert res_alley_s["is_in"] is False
    assert res_alley_d["is_in"] is True

    # Past near baseline (y = 23.98m > 23.77m) -> OUT
    res_out = evaluate_court_point(3.20, 23.98, mode="singles", target_half="near")
    assert res_out["is_in"] is False
    assert res_out["call"] == "OUT"
    assert res_out["closest_line"] == "near_baseline"


def test_homography_roundtrip_and_virtual_court(tmp_path: Path) -> None:
    cal = CourtCalibrator.from_default_camera_geometry(1280, 720)
    u, v = cal.point_court_to_image(5.485, 11.885)
    xm, ym = cal.point_image_to_court(u, v)
    assert abs(xm - 5.485) < 0.05
    assert abs(ym - 11.885) < 0.05

    calib_file = tmp_path / "session.json"
    cal.save(calib_file)
    loaded = CourtCalibrator.load(calib_file)
    assert loaded.H_court_to_img is not None

    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    renderer = VirtualCourtRenderer(loaded, court_mode="singles")
    out = renderer.draw(dummy_frame, draw_doubt_zone=True, draw_anchors=True)
    assert out.shape == dummy_frame.shape
    assert int(np.sum(out)) > 0


def test_tennis_score_engine_deuce_and_game() -> None:
    eng = TennisScoreEngine()
    for _ in range(3):
        eng.award_point(1)
        eng.award_point(2)
    assert eng.get_point_display() == ("40", "40")

    eng.award_point(1)
    assert eng.get_point_display() == ("AD", "40")

    eng.award_point(1)
    assert eng.p1_games == 1
    assert eng.get_point_display() == ("0", "0")


def test_Notebook_is_valid_json() -> None:
    nb_path = Path(__file__).resolve().parents[1] / "Model" / "zeroshot.ipynb"
    data = json.loads(nb_path.read_text(encoding="utf-8"))
    assert data["nbformat"] == 4
    assert len(data["cells"]) >= 7

    webcam_nb_path = Path(__file__).resolve().parents[1] / "Model" / "Tests" / "webcam_test.ipynb"
    if not webcam_nb_path.exists():
        webcam_nb_path = Path(__file__).resolve().parents[1] / "Model" / "webcam_test.ipynb"
    w_data = json.loads(webcam_nb_path.read_text(encoding="utf-8"))
    assert w_data["nbformat"] == 4
    assert len(w_data["cells"]) >= 5


def test_fastapi_studio_endpoints() -> None:
    client = TestClient(app)
    r_index = client.get("/")
    assert r_index.status_code == 200
    assert "CLEAR" in r_index.text

    r_state = client.get("/api/state")
    assert r_state.status_code == 200
    payload = r_state.json()
    assert payload["report"]["line_calling"]["total_bounces"] == 4
    assert payload["report"]["line_calling"]["in_calls"] == 3
    assert payload["report"]["line_calling"]["out_calls"] == 1

    r_judge = client.post("/api/judge-point", json={"u": 640.0, "v": 480.0, "court_mode": "singles"})
    assert r_judge.status_code == 200
    assert r_judge.json()["call"] == "IN"

    r_frame = client.get("/api/frame/110")
    assert r_frame.status_code == 200
    assert r_frame.headers["content-type"] == "image/jpeg"
