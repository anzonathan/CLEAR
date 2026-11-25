"""Package CLEAR analysis runs into a data-analysis bundle (ZIP).

A *run* is one output directory written by ``ClearPipeline.run_video`` (summary.json,
bounces.json, tracks.csv, court_analytics.png). The bundle layout is::

    manifest.json            bundle metadata + one entry per run
    runs.csv                 one row per run (flat summary metrics) -- easy to diff
    <run_id>/manifest.json   run metadata (game, camera, segment, calibration, version)
    <run_id>/summary.json    full pipeline report
    <run_id>/bounces.csv     one row per judged bounce
    <run_id>/tracks.csv      one row per processed frame (ball + players)
    <run_id>/faults.csv      one row per fault event
    <run_id>/court_analytics.png

``notebooks/post_analysis.ipynb`` reads this format (and plain run directories).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

BUNDLE_VERSION = 1

BOUNCE_COLUMNS = [
    "frame_idx", "t_s", "u", "v", "x_m", "y_m", "call", "is_in", "signed_margin_cm",
    "abs_margin_cm", "closest_line", "in_doubt_zone", "confidence", "speed_kmh",
    "court_half", "detector_mode",
]
FAULT_COLUMNS = ["frame_idx", "t_s", "fault_type", "status", "reason", "confidence", "player_id"]
RUN_COLUMNS = [
    "run_id", "label", "game_id", "end", "camera_id", "segment_id", "start_s", "end_s",
    "frames", "fps", "court_mode", "calibration_method", "reproj_error_cm",
    "ball_coverage_pct", "avg_speed_kmh", "max_speed_kmh", "rally_strokes",
    "bounces", "in_calls", "out_calls", "doubt_zone_calls", "fault_events", "score_line",
]


def code_version() -> str:
    """Git commit of the running code (CLEAR_GIT_SHA env wins; 'unknown' if unavailable)."""
    env = os.getenv("CLEAR_GIT_SHA") or os.getenv("SOURCE_COMMIT")
    if env:
        return env[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def safe_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(text)).strip("-") or "run"


def _csv_bytes(columns: List[str], rows: Iterable[Dict[str, object]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return buf.getvalue().encode("utf-8")


def run_summary_row(run_id: str, meta: Dict[str, object], summary: Dict[str, object]) -> Dict[str, object]:
    seg = summary.get("segment") or {}
    cal = summary.get("calibration") or {}
    ball = summary.get("ball_tracking") or {}
    lc = summary.get("line_calling") or {}
    return {
        "run_id": run_id,
        "label": meta.get("label"),
        "game_id": meta.get("game_id"),
        "end": meta.get("end"),
        "camera_id": meta.get("camera_id"),
        "segment_id": meta.get("segment_id"),
        "start_s": seg.get("start_s"),
        "end_s": seg.get("end_s"),
        "frames": summary.get("total_frames"),
        "fps": summary.get("fps"),
        "court_mode": summary.get("court_mode"),
        "calibration_method": cal.get("method"),
        "reproj_error_cm": cal.get("reproj_error_cm"),
        "ball_coverage_pct": ball.get("coverage_pct"),
        "avg_speed_kmh": ball.get("avg_speed_kmh"),
        "max_speed_kmh": ball.get("max_speed_kmh"),
        "rally_strokes": ball.get("rally_strokes"),
        "bounces": lc.get("total_bounces"),
        "in_calls": lc.get("in_calls"),
        "out_calls": lc.get("out_calls"),
        "doubt_zone_calls": lc.get("doubt_zone_calls"),
        "fault_events": len(summary.get("fault_events") or []),
        "score_line": (summary.get("score") or {}).get("score_line"),
    }


def _with_time(rows: List[Dict[str, object]], fps: float) -> List[Dict[str, object]]:
    out = []
    for r in rows:
        r = dict(r)
        if "frame_idx" in r and r["frame_idx"] is not None:
            r["t_s"] = round(int(r["frame_idx"]) / max(1.0, fps), 4)
        out.append(r)
    return out


def add_run(zf: zipfile.ZipFile, run_dir: Path, run_id: str, meta: Dict[str, object]) -> Dict[str, object]:
    """Write one run directory into the open ZIP under ``run_id/``; return its manifest entry."""
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summary.pop("annotated_video", None)  # local server path, meaningless off-box
    fps = float(summary.get("fps") or 60.0)

    bounces_file = run_dir / "bounces.json"
    bounces = (
        json.loads(bounces_file.read_text(encoding="utf-8"))
        if bounces_file.exists()
        else (summary.get("line_calling") or {}).get("bounces", [])
    )
    faults = summary.get("fault_events") or []

    run_meta = {
        "run_id": run_id,
        **meta,
        "segment": summary.get("segment"),
        "fps": fps,
        "total_frames": summary.get("total_frames"),
        "court_mode": summary.get("court_mode"),
        "calibration": {k: v for k, v in (summary.get("calibration") or {}).items() if k != "anchors_px"},
        "code_version": meta.get("code_version") or code_version(),
        "files": ["summary.json", "bounces.csv", "faults.csv"],
    }

    zf.writestr(f"{run_id}/summary.json", json.dumps(summary, indent=2))
    zf.writestr(f"{run_id}/bounces.csv", _csv_bytes(BOUNCE_COLUMNS, _with_time(bounces, fps)))
    zf.writestr(f"{run_id}/faults.csv", _csv_bytes(FAULT_COLUMNS, _with_time(faults, fps)))
    if (run_dir / "tracks.csv").exists():
        zf.write(run_dir / "tracks.csv", f"{run_id}/tracks.csv")
        run_meta["files"].append("tracks.csv")
    if (run_dir / "court_analytics.png").exists():
        zf.write(run_dir / "court_analytics.png", f"{run_id}/court_analytics.png")
        run_meta["files"].append("court_analytics.png")
    zf.writestr(f"{run_id}/manifest.json", json.dumps(run_meta, indent=2))
    return {"run_meta": run_meta, "row": run_summary_row(run_id, meta, summary)}


def build_bundle(
    runs: List[Dict[str, object]],
    bundle_meta: Optional[Dict[str, object]] = None,
) -> bytes:
    """Build the ZIP in memory.

    ``runs`` items: ``{"dir": Path, "run_id": str, "meta": {...}}``. Run directories without a
    summary.json are skipped (and listed under ``skipped`` in the manifest).
    """
    buf = io.BytesIO()
    entries, rows, skipped = [], [], []
    version = code_version()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for run in runs:
            run_dir = Path(run["dir"])
            run_id = safe_id(run["run_id"])
            if not (run_dir / "summary.json").exists():
                skipped.append(run_id)
                continue
            meta = {"code_version": version, **dict(run.get("meta") or {})}
            res = add_run(zf, run_dir, run_id, meta)
            entries.append(res["run_meta"])
            rows.append(res["row"])
        zf.writestr("runs.csv", _csv_bytes(RUN_COLUMNS, rows))
        manifest = {
            "bundle_version": BUNDLE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "code_version": version,
            **(bundle_meta or {}),
            "runs": entries,
            "skipped": skipped,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue()
