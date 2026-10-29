#!/usr/bin/env python3
"""FastAPI backend for CLEAR Interactive Referee & Analytics Studio."""

from __future__ import annotations

import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import quote
import cv2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calibration.court_geometry import ANCHOR_COORDS_M, COURT_LINES_M, SPEC, evaluate_court_point
from src.calibration.homography import CourtCalibrator
from src.data.synthetic_rally import generate_synthetic_clay_rally
from src.pipeline import ClearPipeline
from App.field_api import manager as field_manager, router as field_router
from App.field_auth import field_auth_enabled, protected_path, request_authenticated


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    field_manager.shutdown()


app = FastAPI(
    title="CLEAR: Clay-Court AI Referee Studio",
    version="0.1.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = Path(os.getenv("CLEAR_DATA_DIR", str(ROOT / "data")))
RESULTS_DIR = Path(os.getenv("CLEAR_RESULTS_DIR", str(ROOT / "results")))
CALIB_PATH = Path(os.getenv("CLEAR_CALIB_PATH", str(ROOT / "calib" / "session.json")))

DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CALIB_PATH.parent.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def field_auth_middleware(request, call_next):
    """Optional shared-password gate for the field console and camera links."""
    path = request.url.path
    if (
        field_auth_enabled()
        and protected_path(path)
        and path != "/field/login"
        and not request_authenticated(request)
    ):
        if path.startswith("/api/") or path.startswith("/ws/"):
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        return RedirectResponse(f"/field/login?next={quote(path)}", status_code=303)
    return await call_next(request)


app.include_router(field_router)


@app.get("/api/health")
def health() -> Dict[str, object]:
    return {"ok": True, "service": "clear", "field_ready": True}

# Cache latest pipeline instance in memory for fast frame/telemetry queries
_STATE_CACHE: Dict[str, object] = {}


class CalibrateRequest(BaseModel):
    anchors_px: Dict[str, List[float]]
    court_mode: Literal["singles", "doubles"] = "singles"


class RunPipelineRequest(BaseModel):
    court_mode: Literal["singles", "doubles"] = "singles"
    line_condition: Literal["fresh", "worn", "wiped"] = "worn"
    doubt_zone_cm: float = 15.0
    detector_mode: Literal["hybrid", "yolo", "classical"] = "hybrid"
    use_3frame_temporal: bool = True
    use_parabolic_refinement: bool = True


class PointJudgeRequest(BaseModel):
    u: float
    v: float
    court_mode: Literal["singles", "doubles"] = "singles"


def _ensure_initial_run() -> Dict[str, object]:
    if _STATE_CACHE.get("ready"):
        return _STATE_CACHE

    video_path = DATA_DIR / "demo" / "ucu_clay_rally.mp4"
    gt_path = DATA_DIR / "demo" / "ucu_clay_rally_gt.json"
    if not video_path.exists():
        generate_synthetic_clay_rally(
            video_path=video_path,
            gt_json_path=gt_path,
            calib_json_path=CALIB_PATH,
            line_condition="worn",
        )

    calibrator = (
        CourtCalibrator.load(CALIB_PATH)
        if CALIB_PATH.exists()
        else CourtCalibrator.from_default_camera_geometry()
    )
    pipeline = ClearPipeline(calibrator=calibrator, court_mode="singles", detector_mode="hybrid")
    out_dir = RESULTS_DIR / "rally1"
    report = pipeline.run_video(video_path=video_path, out_dir=out_dir)

    _update_cache(pipeline, report, video_path)
    return _STATE_CACHE


def _update_cache(pipeline: ClearPipeline, report: Dict[str, object], video_path: Path) -> None:
    # Build per-frame telemetry for smooth 60fps HTML5 canvas rendering
    ball_by_f = {s.frame_idx: s for s in pipeline.ball_tracker.history}
    projected_lines = []
    for name, p1_m, p2_m, cat in COURT_LINES_M:
        pts_px = pipeline.calibrator.court_to_image([p1_m, p2_m])
        projected_lines.append(
            {
                "name": name,
                "category": cat,
                "p1_m": list(p1_m),
                "p2_m": list(p2_m),
                "p1_px": [round(float(pts_px[0, 0]), 2), round(float(pts_px[0, 1]), 2)],
                "p2_px": [round(float(pts_px[1, 0]), 2), round(float(pts_px[1, 1]), 2)],
            }
        )

    p1_hist = pipeline.player_tracker.tracks.get(1)
    p2_hist = pipeline.player_tracker.tracks.get(2)
    total_f = int(report.get("total_frames", 280))

    frames_telemetry = []
    for f in range(total_f):
        bs = ball_by_f.get(f)
        p1_xy = (
            p1_hist.court_history_m[min(f, len(p1_hist.court_history_m) - 1)]
            if (p1_hist and p1_hist.court_history_m)
            else (5.485, 22.8)
        )
        p2_xy = (
            p2_hist.court_history_m[min(f, len(p2_hist.court_history_m) - 1)]
            if (p2_hist and p2_hist.court_history_m)
            else (5.485, 1.0)
        )
        p1_uv = pipeline.calibrator.point_court_to_image(*p1_xy)
        p2_uv = pipeline.calibrator.point_court_to_image(*p2_xy)
        frames_telemetry.append(
            {
                "f": f,
                "ball": (
                    {
                        "u": round(bs.u, 1),
                        "v": round(bs.v, 1),
                        "xm": bs.court_x_m,
                        "ym": bs.court_y_m,
                        "kmh": bs.speed_kmh,
                        "pred": bs.is_predicted,
                    }
                    if bs
                    else None
                ),
                "p1": {"u": round(p1_uv[0], 1), "v": round(p1_uv[1], 1), "xm": round(p1_xy[0], 2), "ym": round(p1_xy[1], 2)},
                "p2": {"u": round(p2_uv[0], 1), "v": round(p2_uv[1], 1), "xm": round(p2_xy[0], 2), "ym": round(p2_xy[1], 2)},
            }
        )

    eval_file = RESULTS_DIR / "eval" / "evaluation_metrics.json"
    eval_metrics = json.loads(eval_file.read_text(encoding="utf-8")) if eval_file.exists() else None

    _STATE_CACHE.clear()
    _STATE_CACHE.update(
        {
            "ready": True,
            "video_path": str(video_path),
            "annotated_video_path": str(RESULTS_DIR / "rally1" / "annotated_rally.mp4"),
            "report": report,
            "projected_lines": projected_lines,
            "frames": frames_telemetry,
            "evaluation": eval_metrics,
            "court_spec": {
                "length_m": SPEC.length_m,
                "doubles_width_m": SPEC.doubles_width_m,
                "singles_width_m": SPEC.singles_width_m,
                "alley_width_m": SPEC.alley_width_m,
                "net_y_m": SPEC.net_y_m,
                "far_service_y_m": SPEC.far_service_y_m,
                "near_service_y_m": SPEC.near_service_y_m,
                "center_x_m": SPEC.center_x_m,
            },
        }
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_file = STATIC_DIR / "index.html"
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.get("/api/state")
def get_state() -> Dict[str, object]:
    state = _ensure_initial_run()
    return {
        "report": state["report"],
        "projected_lines": state["projected_lines"],
        "frames": state["frames"],
        "evaluation": state["evaluation"],
        "court_spec": state["court_spec"],
    }


@app.post("/api/calibrate")
def update_calibration(req: CalibrateRequest) -> Dict[str, object]:
    anchors = {k: (float(v[0]), float(v[1])) for k, v in req.anchors_px.items() if k in ANCHOR_COORDS_M}
    if len(anchors) < 4:
        raise HTTPException(status_code=400, detail="At least 4 valid anchors are required.")

    cal = CourtCalibrator(anchors_px=anchors)
    cal.save(CALIB_PATH)

    state = _ensure_initial_run()
    video_path = Path(str(state["video_path"]))
    pipeline = ClearPipeline(calibrator=cal, court_mode=req.court_mode)
    report = pipeline.run_video(video_path=video_path, out_dir=RESULTS_DIR / "rally1")
    _update_cache(pipeline, report, video_path)
    return get_state()


@app.post("/api/run")
def run_pipeline_api(req: RunPipelineRequest) -> Dict[str, object]:
    video_path = DATA_DIR / "demo" / "ucu_clay_rally.mp4"
    gt_path = DATA_DIR / "demo" / "ucu_clay_rally_gt.json"
    generate_synthetic_clay_rally(
        video_path=video_path,
        gt_json_path=gt_path,
        calib_json_path=CALIB_PATH,
        line_condition=req.line_condition,
    )
    cal = CourtCalibrator.load(CALIB_PATH)
    pipeline = ClearPipeline(
        calibrator=cal,
        court_mode=req.court_mode,
        detector_mode=req.detector_mode,
        doubt_zone_cm=req.doubt_zone_cm,
        use_3frame_temporal=req.use_3frame_temporal,
        use_parabolic_refinement=req.use_parabolic_refinement,
    )
    report = pipeline.run_video(video_path=video_path, out_dir=RESULTS_DIR / "rally1")
    _update_cache(pipeline, report, video_path)
    return get_state()


@app.post("/api/judge-point")
def judge_arbitrary_point(req: PointJudgeRequest) -> Dict[str, object]:
    """Allow clicking anywhere on the court canvas to test instant homography + IN/OUT line call."""
    cal = (
        CourtCalibrator.load(CALIB_PATH)
        if CALIB_PATH.exists()
        else CourtCalibrator.from_default_camera_geometry()
    )
    xm, ym = cal.point_image_to_court(req.u, req.v)
    half: Literal["near", "far"] = "far" if ym < SPEC.net_y_m else "near"
    res = evaluate_court_point(
        x_m=xm,
        y_m=ym,
        mode=req.court_mode,
        target_half=half,
        reproj_uncertainty_cm=cal.reproj_error_cm,
    )
    res["u"] = round(req.u, 1)
    res["v"] = round(req.v, 1)
    res["court_half"] = half
    return res


@app.post("/api/upload")
async def upload_custom_video(file: UploadFile = File(...)) -> Dict[str, object]:
    dest = DATA_DIR / "uploaded_rally.mp4"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    cal = (
        CourtCalibrator.load(CALIB_PATH)
        if CALIB_PATH.exists()
        else CourtCalibrator.from_default_camera_geometry()
    )
    pipeline = ClearPipeline(calibrator=cal)
    report = pipeline.run_video(video_path=dest, out_dir=RESULTS_DIR / "rally1")
    _update_cache(pipeline, report, dest)
    return get_state()


@app.get("/api/frame/{frame_idx}")
def get_annotated_frame(frame_idx: int) -> Response:
    state = _ensure_initial_run()
    vid_file = Path(str(state["annotated_video_path"]))
    if not vid_file.exists():
        raise HTTPException(status_code=404, detail="Annotated video not found.")

    cap = cv2.VideoCapture(str(vid_file))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = int(max(0, min(total - 1, frame_idx)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise HTTPException(status_code=404, detail="Frame could not be decoded.")

    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode frame.")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/api/chart")
def get_analytics_chart() -> FileResponse:
    _ensure_initial_run()
    chart = RESULTS_DIR / "rally1" / "court_analytics.png"
    if not chart.exists():
        raise HTTPException(status_code=404, detail="Chart not generated yet.")
    return FileResponse(chart, media_type="image/png")


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8090")))
