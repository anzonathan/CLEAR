import json

import cv2
import numpy as np

from src.capture.recorder import RecordingSession


def test_pause_drops_frames_and_resume_writes_into_same_file(tmp_path):
    session = RecordingSession("rec_t", "test", tmp_path, fps=10)
    rec = session.add_camera("cam1")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    for _ in range(5):
        rec.write(frame, frame)
    session.set_paused(True)
    for _ in range(7):
        rec.write(frame, frame)  # dropped
    session.set_paused(False)
    for _ in range(3):
        rec.write(frame, frame)

    assert rec.frame_count == 8
    meta = session.finalize()
    assert json.loads((tmp_path / "recordings" / "rec_t" / "meta.json").read_text())["cameras"][0]["frames"] == 8
    cap = cv2.VideoCapture(str(rec.raw_path))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 8
    cap.release()
    assert meta["cameras"][0]["camera_id"] == "cam1"


def test_pause_applies_to_cameras_added_before_it(tmp_path):
    session = RecordingSession("rec_u", "test", tmp_path, fps=10)
    a, b = session.add_camera("a"), session.add_camera("b")
    session.set_paused(True)
    assert a.paused and b.paused and session.paused
