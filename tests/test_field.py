"""Field capture, channel switching, court auto-detection, and deployment API/WebSocket tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import App.field_api as field_api
import App.server as server_mod
from App.server import app
from src.calibration.auto_court import anchors_from_quad, detect_court_quad, order_court_quad
from src.capture.manager import FieldManager


def test_registry_persists_and_tokens(tmp_path: Path) -> None:
    manager = FieldManager(tmp_path)
    first = manager.create_camera("Court A", "browser")
    second = manager.create_camera("Court B", "rtsp", "rtsp://example/stream")

    assert manager.get_camera_by_token(first["token"])["id"] == first["id"]
    assert manager.registry.token_matches(str(second["id"]), str(second["token"]))
    assert not manager.registry.token_matches(str(second["id"]), "wrong")

    reloaded = FieldManager(tmp_path)
    assert len(reloaded.list_cameras()) == 2


def test_only_one_active_channel(tmp_path: Path) -> None:
    manager = FieldManager(tmp_path)
    first = manager.create_camera("Court A", "browser")
    second = manager.create_camera("Court B", "browser")

    manager.activate(str(first["id"]))
    runtime_a = manager.runtime
    assert manager.active_id == first["id"]
    assert runtime_a is not None

    manager.activate(str(second["id"]))
    assert manager.active_id == second["id"]
    assert manager.runtime is not runtime_a
    assert runtime_a.stop_event.is_set()
    assert manager.get_camera(str(first["id"]))["active"] is False

    manager.deactivate()
    assert manager.active_id is None


def test_manual_calibration_saved_per_camera(tmp_path: Path) -> None:
    manager = FieldManager(tmp_path)
    camera = manager.create_camera("Court A", "browser")
    anchors = {
        "far_left_doubles": [250.0, 120.0],
        "far_right_doubles": [710.0, 120.0],
        "near_right_doubles": [860.0, 470.0],
        "near_left_doubles": [100.0, 470.0],
    }
    cal = manager.save_calibration(str(camera["id"]), anchors, method="manual")
    assert cal is not None
    assert cal.H_court_to_img is not None
    assert manager.registry.calibration_path(str(camera["id"])).exists()
    assert manager.get_calibration(str(camera["id"]))["method"] == "manual"


def test_auto_court_quad_on_synthetic_outline() -> None:
    frame = np.full((540, 960, 3), (60, 90, 150), dtype=np.uint8)
    quad = np.array([[250, 120], [710, 120], [860, 470], [100, 470]], dtype=np.int32)
    cv2.polylines(frame, [quad], True, (245, 245, 245), 5)
    cv2.line(frame, (300, 295), (660, 295), (245, 245, 245), 3)

    detected, confidence, _ = detect_court_quad(frame)
    assert detected is not None
    assert confidence > 0.5
    ordered = order_court_quad(detected)
    anchors = anchors_from_quad(ordered)
    assert set(anchors) == {
        "far_left_doubles",
        "far_right_doubles",
        "near_right_doubles",
        "near_left_doubles",
    }


def _make_synthetic_court_jpeg() -> bytes:
    frame = np.full((540, 960, 3), (60, 90, 150), dtype=np.uint8)
    quad = np.array([[250, 120], [710, 120], [860, 470], [100, 470]], dtype=np.int32)
    cv2.polylines(frame, [quad], True, (245, 245, 245), 5)
    cv2.line(frame, (300, 295), (660, 295), (245, 245, 245), 3)
    # Draw optic-yellow tennis ball on clay
    cv2.circle(frame, (480, 310), 7, (40, 235, 225), -1)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    assert ok
    return buf.tobytes()


def test_field_api_and_websocket_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLEAR_FIELD_PASSWORD", raising=False)
    temp_manager = FieldManager(tmp_path)
    monkeypatch.setattr(field_api, "manager", temp_manager)
    monkeypatch.setattr(server_mod, "field_manager", temp_manager)

    with TestClient(app) as client:
        # 1. Health endpoints
        r_health = client.get("/api/health")
        assert r_health.status_code == 200
        assert r_health.json()["ok"] is True

        r_fhealth = client.get("/api/field/health")
        assert r_fhealth.status_code == 200
        assert r_fhealth.json()["auth_enabled"] is False

        # 2. Field console HTML
        r_field = client.get("/field")
        assert r_field.status_code == 200
        assert "Field Detection Console" in r_field.text

        # 3. Create browser camera channel
        r_create = client.post("/api/field/cameras", json={"name": "UCU Court 1", "source": "browser"})
        assert r_create.status_code == 200
        cam = r_create.json()
        cam_id = cam["id"]
        token = cam["token"]

        # 4. Phone camera page
        r_cam_page = client.get(f"/camera/{token}")
        assert r_cam_page.status_code == 200
        assert "UCU Court 1" in r_cam_page.text
        assert client.get("/camera/invalid_token").status_code == 404

        # 5. Activate channel + ingest frame over WebSocket
        r_act = client.post(f"/api/field/cameras/{cam_id}/activate")
        assert r_act.status_code == 200
        assert r_act.json()["active"] is True

        jpeg_bytes = _make_synthetic_court_jpeg()
        with client.websocket_connect(f"/ws/field/ingest/{cam_id}?token={token}") as ws_in:
            status_msg = json.loads(ws_in.receive_text())
            assert status_msg["type"] == "status"
            assert status_msg["active"] is True
            ws_in.send_bytes(jpeg_bytes)

            # Wait briefly for background inference worker to process frame
            deadline = time.time() + 3.0
            while time.time() < deadline:
                active_info = client.get("/api/field/active").json()["camera"]
                if active_info and active_info.get("frame_index", 0) >= 1:
                    break
                time.sleep(0.05)

            # 6. Verify viewer WebSocket receives annotated JPEG + metadata
            with client.websocket_connect(f"/ws/field/view/{cam_id}") as ws_view:
                first_msg = ws_view.receive()
                if first_msg.get("bytes") is not None:
                    assert first_msg["bytes"][:2] == b"\xff\xd8"
                    meta_msg = json.loads(ws_view.receive_text())
                else:
                    meta_msg = json.loads(first_msg["text"])
                assert meta_msg["type"] == "meta"
                assert meta_msg["camera"]["id"] == cam_id

            # 7. Auto calibration on live synthetic frame
            r_auto = client.post(f"/api/field/cameras/{cam_id}/calibration/auto")
            assert r_auto.status_code == 200
            assert r_auto.json()["method"] == "auto"

            # 8. Update detector thresholds & overlays live
            r_patch = client.patch(
                f"/api/field/cameras/{cam_id}",
                json={"court_mode": "doubles", "detector": {"person": 0.4, "racket": 0.3, "ball": 0.2}},
            )
            assert r_patch.status_code == 200
            assert r_patch.json()["court_mode"] == "doubles"

            # 9. Snapshot download and save
            r_snap_raw = client.get(f"/api/field/cameras/{cam_id}/snapshot.jpg?raw=true")
            assert r_snap_raw.status_code == 200
            assert r_snap_raw.headers["content-type"] == "image/jpeg"

            r_save_snap = client.post(f"/api/field/cameras/{cam_id}/snapshot")
            assert r_save_snap.status_code == 200
            assert r_save_snap.json()["ok"] is True

            # 10. Events log
            r_events = client.get(f"/api/field/cameras/{cam_id}/events")
            assert r_events.status_code == 200
            event_types = {e["event"] for e in r_events.json()["events"]}
            assert "activate" in event_types
            assert "snapshot" in event_types

        # 11. Deactivate and delete
        assert client.post("/api/field/deactivate").status_code == 200
        assert client.delete(f"/api/field/cameras/{cam_id}").status_code == 200


def test_field_password_auth_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLEAR_FIELD_PASSWORD", "ucu-secret-2026")
    temp_manager = FieldManager(tmp_path)
    cam = temp_manager.create_camera("Auth Court", "browser")
    monkeypatch.setattr(field_api, "manager", temp_manager)
    monkeypatch.setattr(server_mod, "field_manager", temp_manager)

    with TestClient(app) as client:
        # Docker healthcheck must stay open even when password is set
        assert client.get("/api/health").status_code == 200

        # Protected API and pages require auth
        assert client.get("/api/field/cameras").status_code == 401
        r_redir = client.get("/field", follow_redirects=False)
        assert r_redir.status_code == 303
        assert r_redir.headers["location"].startswith("/field/login")

        r_cam_redir = client.get(f"/camera/{cam['token']}", follow_redirects=False)
        assert r_cam_redir.status_code == 303
        assert "/camera/" in r_cam_redir.headers["location"]

        # Wrong password rejected
        r_bad = client.post("/field/login", data={"password": "wrong", "next": "/field"})
        assert r_bad.status_code == 401

        # Correct password sets cookie and unlocks routes
        r_ok = client.post(
            "/field/login",
            data={"password": "ucu-secret-2026", "next": f"/camera/{cam['token']}"},
            follow_redirects=False,
        )
        assert r_ok.status_code == 303
        assert r_ok.headers["location"] == f"/camera/{cam['token']}"
        assert "clear_field_auth" in client.cookies

        assert client.get("/api/field/cameras").status_code == 200
        assert client.get(f"/camera/{cam['token']}").status_code == 200

