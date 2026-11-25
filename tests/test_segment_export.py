import csv
import io
import json
import zipfile
from pathlib import Path

from src.analysis_export import build_bundle
from src.pipeline import TRACK_COLUMNS, ClearPipeline

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo" / "ucu_clay_rally.mp4"


def test_segment_keeps_absolute_frames_and_writes_tracks(tmp_path):
    report = ClearPipeline().run_video(DEMO, tmp_path, start_frame=60, end_frame=120)

    assert report["total_frames"] == 60
    assert report["segment"]["start_frame"] == 60
    assert report["segment"]["end_frame"] == 120
    rows = list(csv.DictReader((tmp_path / "tracks.csv").open()))
    assert list(rows[0]) == TRACK_COLUMNS
    assert [int(r["frame_idx"]) for r in (rows[0], rows[-1])] == [60, 119]
    for b in json.loads((tmp_path / "bounces.json").read_text()):
        assert 60 <= b["frame_idx"] < 120


def test_bundle_layout(tmp_path):
    ClearPipeline().run_video(DEMO, tmp_path / "run", max_frames=30)
    data = build_bundle([{"dir": tmp_path / "run", "run_id": "end a/full", "meta": {"label": "Full"}},
                         {"dir": tmp_path / "missing", "run_id": "gone", "meta": {}}])
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    assert {"manifest.json", "runs.csv", "end-a-full/summary.json", "end-a-full/bounces.csv",
            "end-a-full/tracks.csv", "end-a-full/faults.csv", "end-a-full/manifest.json"} <= names
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["skipped"] == ["gone"]
    assert manifest["runs"][0]["label"] == "Full"
    assert "annotated_video" not in json.loads(z.read("end-a-full/summary.json"))
    runs = list(csv.DictReader(io.StringIO(z.read("runs.csv").decode())))
    assert runs[0]["run_id"] == "end-a-full" and runs[0]["frames"] == "30"
