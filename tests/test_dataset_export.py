"""Labelling-dataset export: trimmed raw/overlay clips, sampled frames, YOLO pre-labels, metadata."""

import csv
import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src import dataset_export as dx
from src.detect.detector import BallDetection, FrameDetections, PlayerDetection

FPS = 10.0
SIZE = (160, 90)


def _video(path: Path, frames: int, shade: int = 0) -> Path:
    """Each frame's top-left pixel encodes its frame number, so trims can be checked."""
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SIZE)
    for i in range(frames):
        img = np.full((SIZE[1], SIZE[0], 3), shade, dtype=np.uint8)
        _stamp(img, i)
        w.write(img)
    w.release()
    return path


def _stamp(img: np.ndarray, i: int) -> None:
    """Write frame number i as 6 black/white blocks, readable after lossy re-encodes."""
    for b in range(6):
        img[0:16, b * 24:b * 24 + 16] = 255 if (i >> b) & 1 else 0


def _read_stamp(img: np.ndarray) -> int:
    return sum(1 << b for b in range(6) if img[8, b * 24 + 8].mean() > 128)


def _count(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    return n


class FakeDetector:
    def __init__(self):
        self.calls = 0

    def reset(self):
        pass

    def detect(self, frame, idx):
        self.calls += 1
        return FrameDetections(
            frame_idx=idx,
            balls=[BallDetection(u=80, v=45, radius=3, conf=0.9)],
            players=[PlayerDetection(bbox=(10, 10, 50, 80), conf=0.8, foot_uv=(30, 80))],
        )


def _clip(tmp: Path, **over):
    clip = {
        "clip_id": "g1_end_a_s1",
        "label": "Rally 1",
        "start_s": 1.0,
        "end_s": 3.0,
        "raw_path": _video(tmp / "cam_raw.mp4", 50),
        "live_overlay_path": _video(tmp / "cam_annot.mp4", 50, shade=200),
        "analysis_dir": None,
        "analysis_overlay_path": None,
        "calibration_path": None,
        "meta": {"game_id": "g1", "end": "end_a", "players": ["Ann", "Bo"], "camera_id": "cam"},
    }
    clip.update(over)
    return clip


def test_sample_frames_step_and_cap():
    assert dx.sample_frames(10, 30, 10.0, 2.0) == [10, 15, 20, 25]
    assert dx.sample_frames(0, 10, 10.0, 0) == []
    many = dx.sample_frames(0, 10 ** 6, 30.0, 30.0)
    assert len(many) == dx.MAX_FRAMES_PER_CLIP


def test_clean_options_clamps_and_drops_labels_without_frames():
    o = dx.clean_options({"frames_fps": 99, "jpeg_quality": 5, "raw": 0})
    assert o["frames_fps"] == 30 and o["jpeg_quality"] == 50 and o["raw"] is False
    assert dx.clean_options({"frames_fps": 0, "prelabels": True})["prelabels"] is False


def test_yolo_lines_normalised_and_clipped():
    dets = FrameDetections(
        frame_idx=0,
        balls=[BallDetection(u=2, v=2, radius=2, conf=1)],
        players=[PlayerDetection(bbox=(80, 0, 240, 90), conf=1, foot_uv=(0, 0))],
    )
    lines = dx.yolo_lines(dets, 160, 90)
    assert lines[0].startswith("0 ")  # ball box clipped at the image edge
    cls, cx, cy, w, h = lines[1].split()
    assert cls == "1" and float(cx) == pytest.approx(0.75) and float(w) == pytest.approx(0.5)


def test_build_dataset_trims_and_indexes(tmp_path, monkeypatch):
    fake = FakeDetector()
    monkeypatch.setattr("src.detect.detector.HybridTennisDetector", lambda **_: fake)
    out = tmp_path / "out.zip"
    res = dx.build_dataset([_clip(tmp_path)], {"frames_fps": 2}, out, tmp_path / "work")

    assert res["clips"] == 1 and res["failed_clips"] == 0
    assert res["frames"] == 4 and res["labelled_frames"] == 4  # frames 10, 15, 20, 25
    assert not (tmp_path / "work").exists()

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        for f in ("manifest.json", "clips.csv", "frames.csv", "README.md", "roboflow/data.yaml",
                  "clips/g1_end_a_s1/raw.mp4", "clips/g1_end_a_s1/overlay.mp4", "clips/g1_end_a_s1/meta.json",
                  "roboflow/images/g1_end_a_s1_f000010.jpg", "roboflow/labels/g1_end_a_s1_f000025.txt"):
            assert f in names, f
        meta = json.loads(zf.read("clips/g1_end_a_s1/meta.json"))
        assert (meta["start_frame"], meta["end_frame"]) == (10, 30)
        assert meta["overlay_source"] == "live" and meta["game_id"] == "g1"
        frames = list(csv.DictReader(io.StringIO(zf.read("frames.csv").decode())))
        assert [int(r["frame_idx"]) for r in frames] == [10, 15, 20, 25]
        assert frames[1]["clip_frame"] == "5"
        label = zf.read("roboflow/labels/g1_end_a_s1_f000010.txt").decode().splitlines()
        assert [ln.split()[0] for ln in label] == ["0", "1"]
        assert "names: [ball, player, racket]" in zf.read("roboflow/data.yaml").decode()
        zf.extract("clips/g1_end_a_s1/raw.mp4", tmp_path / "x")
        zf.extract("clips/g1_end_a_s1/overlay.mp4", tmp_path / "x")

    raw = tmp_path / "x/clips/g1_end_a_s1/raw.mp4"
    assert _count(raw) == 20
    cap = cv2.VideoCapture(str(raw))
    ok, first = cap.read()
    cap.release()
    # The first clip frame is source frame 10.
    assert ok and _read_stamp(first) == 10
    assert _count(tmp_path / "x/clips/g1_end_a_s1/overlay.mp4") == 20


def test_analysis_overlay_preferred_and_offset(tmp_path, monkeypatch):
    # Segment analysis overlay starts at source frame 10, so clip frame 0 is its frame 0.
    seg_ov = _video(tmp_path / "annotated_rally.mp4", 20, shade=120)
    clip = _clip(tmp_path, analysis_overlay_path=seg_ov, analysis_overlay_start_frame=10)
    out = tmp_path / "out.zip"
    dx.build_dataset([clip], {"frames_fps": 0}, out, tmp_path / "work")
    with zipfile.ZipFile(out) as zf:
        meta = json.loads(zf.read("clips/g1_end_a_s1/meta.json"))
        assert meta["overlay_source"] == "analysis"
        assert not any(n.startswith("roboflow/images/") for n in zf.namelist())
        zf.extract("clips/g1_end_a_s1/overlay.mp4", tmp_path / "x")
    cap = cv2.VideoCapture(str(tmp_path / "x/clips/g1_end_a_s1/overlay.mp4"))
    ok, first = cap.read()
    cap.release()
    assert ok and _read_stamp(first) == 0  # overlay frame 0 = source frame 10


def test_missing_recording_fails_clip_not_export(tmp_path):
    good = _clip(tmp_path)
    bad = _clip(tmp_path, clip_id="bad", raw_path=tmp_path / "nope.mp4")
    out = tmp_path / "out.zip"
    res = dx.build_dataset([bad, good], {"frames_fps": 0, "overlay": False}, out, tmp_path / "work")
    assert res["clips"] == 2 and res["failed_clips"] == 1
    with zipfile.ZipFile(out) as zf:
        assert "missing" in json.loads(zf.read("clips/bad/meta.json"))["error"]
        assert "clips/g1_end_a_s1/raw.mp4" in zf.namelist()
