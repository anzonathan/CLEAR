"""Load and compare CLEAR post-video analysis runs.

Sources accepted by :func:`load_runs`:

* export ZIPs downloaded from the dev game page (``Export selected`` / ``Export all``),
* unzipped export folders (containing ``manifest.json`` + one folder per run),
* plain pipeline output folders (``summary.json`` [+ ``bounces.json``, ``tracks.csv``]),
  e.g. ``results/eval/final`` or the output of ``scripts/infer.py``.

Everything is returned as tidy pandas DataFrames keyed by ``run_id``.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# ITF court, metres (same frame as src/calibration/court_geometry.py:
# x across the court 0..10.97, y along it 0..23.77, net at y = 11.885).
COURT_LENGTH_M = 23.77
DOUBLES_WIDTH_M = 10.97
SINGLES_WIDTH_M = 8.23
ALLEY_M = (DOUBLES_WIDTH_M - SINGLES_WIDTH_M) / 2
NET_Y_M = COURT_LENGTH_M / 2
SERVICE_OFFSET_M = 6.40
CENTER_X_M = DOUBLES_WIDTH_M / 2

SUMMARY_METRICS = [
    "frames", "duration_s", "ball_coverage_pct", "avg_speed_kmh", "max_speed_kmh",
    "rally_strokes", "bounces", "in_calls", "out_calls", "doubt_zone_calls",
    "doubt_rate_pct", "fault_events", "reproj_error_cm",
]


@dataclass
class Runs:
    runs: pd.DataFrame
    bounces: pd.DataFrame
    tracks: pd.DataFrame
    faults: pd.DataFrame
    summaries: Dict[str, dict] = field(default_factory=dict)

    def ids(self) -> List[str]:
        return list(self.runs["run_id"])


# --------------------------------------------------------------------------- loading
def _read_json(blob: bytes | str) -> dict:
    return json.loads(blob)


def _run_row(run_id: str, source: str, summary: dict, meta: dict) -> dict:
    seg = summary.get("segment") or {}
    cal = summary.get("calibration") or {}
    ball = summary.get("ball_tracking") or {}
    lc = summary.get("line_calling") or {}
    fps = float(summary.get("fps") or meta.get("fps") or 60.0)
    frames = int(summary.get("total_frames") or 0)
    bounces = int(lc.get("total_bounces") or 0)
    doubt = int(lc.get("doubt_zone_calls") or 0)
    return {
        "run_id": run_id,
        "label": meta.get("label") or run_id,
        "source": source,
        "game_id": meta.get("game_id"),
        "end": meta.get("end"),
        "camera_id": meta.get("camera_id"),
        "segment_id": meta.get("segment_id"),
        "start_s": seg.get("start_s", 0.0),
        "end_s": seg.get("end_s", round(frames / fps, 3)),
        "fps": fps,
        "frames": frames,
        "duration_s": round(frames / fps, 3),
        "court_mode": summary.get("court_mode"),
        "calibration_method": cal.get("method"),
        "reproj_error_cm": cal.get("reproj_error_cm"),
        "calibrated": meta.get("calibrated"),
        "code_version": meta.get("code_version"),
        "ball_coverage_pct": ball.get("coverage_pct"),
        "avg_speed_kmh": ball.get("avg_speed_kmh"),
        "max_speed_kmh": ball.get("max_speed_kmh"),
        "rally_strokes": ball.get("rally_strokes"),
        "bounces": bounces,
        "in_calls": lc.get("in_calls"),
        "out_calls": lc.get("out_calls"),
        "doubt_zone_calls": doubt,
        "doubt_rate_pct": round(100.0 * doubt / bounces, 1) if bounces else 0.0,
        "fault_events": len(summary.get("fault_events") or []),
        "score_line": (summary.get("score") or {}).get("score_line"),
    }


def _frame_tables(run_id: str, summary: dict, bounces: Optional[list],
                  tracks_csv: Optional[bytes]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fps = float(summary.get("fps") or 60.0)
    if bounces is None:
        bounces = (summary.get("line_calling") or {}).get("bounces") or []
    b = pd.DataFrame(bounces)
    if not b.empty:
        b.insert(0, "run_id", run_id)
        b["t_s"] = b["frame_idx"] / fps
    f = pd.DataFrame(summary.get("fault_events") or [])
    if not f.empty:
        f.insert(0, "run_id", run_id)
        f["t_s"] = f["frame_idx"] / fps
    t = pd.read_csv(io.BytesIO(tracks_csv)) if tracks_csv else pd.DataFrame()
    if not t.empty:
        t.insert(0, "run_id", run_id)
    return b, t, f


def _unique(run_id: str, taken: set) -> str:
    rid, n = run_id, 2
    while rid in taken:
        rid, n = f"{run_id}~{n}", n + 1
    taken.add(rid)
    return rid


def _iter_bundle(read, names: Iterable[str], source: str):
    """Yield (run_id, meta, summary, bounces, tracks_csv) from an export bundle."""
    manifest = _read_json(read("manifest.json"))
    names = set(names)
    for meta in manifest.get("runs", []):
        rid = meta["run_id"]
        summary = _read_json(read(f"{rid}/summary.json"))
        tracks = read(f"{rid}/tracks.csv") if f"{rid}/tracks.csv" in names else None
        yield rid, meta, summary, None, tracks


def _iter_source(path: Path):
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            yield from _iter_bundle(zf.read, zf.namelist(), str(path))
    elif (path / "manifest.json").exists() and json.loads((path / "manifest.json").read_text()).get("runs") is not None:
        names = [str(p.relative_to(path)).replace("\\", "/") for p in path.rglob("*") if p.is_file()]
        yield from _iter_bundle(lambda n: (path / n).read_bytes(), names, str(path))
    elif (path / "summary.json").exists():
        summary = json.loads((path / "summary.json").read_text())
        bounces = json.loads((path / "bounces.json").read_text()) if (path / "bounces.json").exists() else None
        tracks = (path / "tracks.csv").read_bytes() if (path / "tracks.csv").exists() else None
        rid = path.name if path.parent.name in ("", ".") else f"{path.parent.name}/{path.name}"
        yield rid, {"label": rid}, summary, bounces, tracks
    else:
        raise ValueError(f"Not a CLEAR export or run folder: {path}")


def load_runs(sources: Iterable[str | Path]) -> Runs:
    rows, bs, ts, fs, sums, taken = [], [], [], [], {}, set()
    for src in sources:
        for rid, meta, summary, bounces, tracks in _iter_source(Path(src)):
            # Bundles from different games can reuse run ids like "end_a_full".
            rid = _unique(f"{meta['game_id']}:{rid}" if meta.get("game_id") else rid, taken)
            rows.append(_run_row(rid, str(src), summary, meta))
            b, t, f = _frame_tables(rid, summary, bounces, tracks)
            bs.append(b), ts.append(t), fs.append(f)
            sums[rid] = summary
    cat = lambda dfs: pd.concat([d for d in dfs if not d.empty], ignore_index=True) if any(not d.empty for d in dfs) else pd.DataFrame()
    return Runs(pd.DataFrame(rows), cat(bs), cat(ts), cat(fs), sums)


def find_sources(*dirs: str | Path) -> List[Path]:
    """Every export ZIP / export folder / run folder directly inside the given directories."""
    out: List[Path] = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        if (d / "summary.json").exists() or (d / "manifest.json").exists():
            out.append(d)
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() == ".zip" or (p / "summary.json").exists() or (p / "manifest.json").exists():
                out.append(p)
    return out


# --------------------------------------------------------------------------- comparing
def summary_table(runs: Runs) -> pd.DataFrame:
    cols = ["label", "end", "start_s", "end_s"] + SUMMARY_METRICS
    return runs.runs.set_index("run_id")[[c for c in cols if c in runs.runs.columns]]


def match_bounces(a: pd.DataFrame, b: pd.DataFrame, tol_s: float = 0.15) -> pd.DataFrame:
    """One-to-one match of two runs' bounces by time (closest pairs first, within ``tol_s``).

    Returns one row per bounce in either run: matched pairs side by side, plus unmatched
    bounces with the other side empty (``status`` = matched / only_a / only_b).
    """
    a = a.reset_index(drop=True)
    b = b.reset_index(drop=True)
    pairs = []
    if len(a) and len(b):
        dt = np.abs(a["t_s"].to_numpy()[:, None] - b["t_s"].to_numpy()[None, :])
        cand = np.argwhere(dt <= tol_s)
        cand = cand[np.argsort(dt[cand[:, 0], cand[:, 1]])]
        used_a, used_b = set(), set()
        for i, j in cand:
            if i in used_a or j in used_b:
                continue
            used_a.add(i), used_b.add(j)
            pairs.append((i, j))
    keep = ["t_s", "frame_idx", "x_m", "y_m", "call", "is_in", "signed_margin_cm",
            "in_doubt_zone", "confidence", "speed_kmh", "court_half"]
    keep = [k for k in keep if k in a.columns or k in b.columns]

    def side(df, idx, suffix):
        if idx is None:
            return {f"{k}_{suffix}": np.nan for k in keep}
        return {f"{k}_{suffix}": df.at[idx, k] if k in df.columns else np.nan for k in keep}

    rows = [{"status": "matched", **side(a, i, "a"), **side(b, j, "b")} for i, j in pairs]
    ma = {i for i, _ in pairs}
    mb = {j for _, j in pairs}
    rows += [{"status": "only_a", **side(a, i, "a"), **side(b, None, "b")} for i in range(len(a)) if i not in ma]
    rows += [{"status": "only_b", **side(a, None, "a"), **side(b, j, "b")} for j in range(len(b)) if j not in mb]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    m = out["status"] == "matched"
    out.loc[m, "dt_ms"] = (out.loc[m, "t_s_b"] - out.loc[m, "t_s_a"]) * 1000
    out.loc[m, "pos_diff_cm"] = np.hypot(out.loc[m, "x_m_b"] - out.loc[m, "x_m_a"],
                                         out.loc[m, "y_m_b"] - out.loc[m, "y_m_a"]) * 100
    out.loc[m, "call_agrees"] = out.loc[m, "call_a"] == out.loc[m, "call_b"]
    out.loc[m, "speed_diff_kmh"] = out.loc[m, "speed_kmh_b"] - out.loc[m, "speed_kmh_a"]
    sort_t = out["t_s_a"].fillna(out["t_s_b"])
    return out.assign(_t=sort_t).sort_values("_t").drop(columns="_t").reset_index(drop=True)


def bounce_agreement(matched: pd.DataFrame) -> pd.Series:
    """Headline numbers for a :func:`match_bounces` table."""
    if matched.empty:
        return pd.Series({"bounces_a": 0, "bounces_b": 0, "matched": 0})
    m = matched[matched["status"] == "matched"]
    n_a = int((matched["status"] != "only_b").sum())
    n_b = int((matched["status"] != "only_a").sum())
    return pd.Series({
        "bounces_a": n_a,
        "bounces_b": n_b,
        "matched": len(m),
        "only_a": int((matched["status"] == "only_a").sum()),
        "only_b": int((matched["status"] == "only_b").sum()),
        "recall_b_vs_a_pct": round(100 * len(m) / n_a, 1) if n_a else np.nan,
        "precision_b_vs_a_pct": round(100 * len(m) / n_b, 1) if n_b else np.nan,
        "call_agreement_pct": round(100 * m["call_agrees"].mean(), 1) if len(m) else np.nan,
        "median_pos_diff_cm": round(m["pos_diff_cm"].median(), 1) if len(m) else np.nan,
        "p90_pos_diff_cm": round(m["pos_diff_cm"].quantile(0.9), 1) if len(m) else np.nan,
        "median_abs_dt_ms": round(m["dt_ms"].abs().median(), 1) if len(m) else np.nan,
        "median_speed_diff_kmh": round(m["speed_diff_kmh"].median(), 1) if len(m) else np.nan,
    })


def compare_tracks(tracks: pd.DataFrame, run_a: str, run_b: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Frame-by-frame join of two runs' ball tracks (same source video / frame numbering)."""
    if tracks.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    cols = ["frame_idx", "t_s", "ball_state", "ball_x_m", "ball_y_m", "ball_speed_kmh"]
    a = tracks[tracks["run_id"] == run_a][cols]
    b = tracks[tracks["run_id"] == run_b][cols]
    if a.empty or b.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    j = a.merge(b, on="frame_idx", suffixes=("_a", "_b"), how="outer").sort_values("frame_idx")
    both = j[(j["ball_state_a"] == "detected") & (j["ball_state_b"] == "detected")]
    d = np.hypot(both["ball_x_m_b"] - both["ball_x_m_a"], both["ball_y_m_b"] - both["ball_y_m_a"]) * 100
    common = j["ball_state_a"].notna() & j["ball_state_b"].notna()
    stats = pd.Series({
        "common_frames": int(common.sum()),
        "detected_a_pct": round(100 * (j.loc[common, "ball_state_a"] == "detected").mean(), 1) if common.any() else np.nan,
        "detected_b_pct": round(100 * (j.loc[common, "ball_state_b"] == "detected").mean(), 1) if common.any() else np.nan,
        "both_detected_frames": len(both),
        "median_ball_pos_diff_cm": round(d.median(), 1) if len(d) else np.nan,
        "rmse_ball_pos_cm": round(float(np.sqrt((d ** 2).mean())), 1) if len(d) else np.nan,
    })
    return j, stats


# --------------------------------------------------------------------------- plotting
def draw_court(ax, singles: bool = True, color: str = "#c8d2c8"):
    """ITF court outline in metres (x across, y along; near baseline at the bottom)."""
    kw = dict(color=color, lw=1.2, zorder=0)
    W, L = DOUBLES_WIDTH_M, COURT_LENGTH_M
    ax.plot([0, W, W, 0, 0], [0, 0, L, L, 0], **kw)
    for x in (ALLEY_M, W - ALLEY_M):
        ax.plot([x, x], [0, L], **kw)
    for y in (NET_Y_M - SERVICE_OFFSET_M, NET_Y_M + SERVICE_OFFSET_M):
        ax.plot([ALLEY_M, W - ALLEY_M], [y, y], **kw)
    ax.plot([CENTER_X_M, CENTER_X_M], [NET_Y_M - SERVICE_OFFSET_M, NET_Y_M + SERVICE_OFFSET_M], **kw)
    ax.plot([-0.9, W + 0.9], [NET_Y_M, NET_Y_M], color="#68766e", lw=2, zorder=0)
    ax.set_xlim(-2.5, W + 2.5)
    ax.set_ylim(L + 3, -3)  # far end at the top, like the broadcast view
    ax.set_aspect("equal")
    ax.set_xticks([]), ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return ax
