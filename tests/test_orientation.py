import cv2
import numpy as np

from src.orientation import ensure_landscape, landscape_size


def test_portrait_frame_is_rotated_to_landscape():
    frame = np.zeros((720, 405, 3), dtype=np.uint8)
    out = ensure_landscape(frame)
    assert out.shape[:2] == (405, 720)


def test_landscape_frame_is_untouched():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert ensure_landscape(frame) is frame


def test_landscape_size():
    assert landscape_size(405, 720) == (720, 405)
    assert landscape_size(1280, 720) == (1280, 720)


def test_pipeline_writes_landscape_video_for_portrait_input(tmp_path):
    from src.pipeline import ClearPipeline

    src = tmp_path / "portrait.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (360, 640))
    for _ in range(5):
        writer.write(np.full((640, 360, 3), 80, dtype=np.uint8))
    writer.release()

    ClearPipeline().run_video(src, tmp_path / "out", max_frames=5)

    cap = cv2.VideoCapture(str(tmp_path / "out" / "annotated_rally.mp4"))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, frame = cap.read()
    cap.release()
    assert (w, h) == (640, 360)
    assert ok and frame.shape[:2] == (360, 640)
