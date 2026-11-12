"""Field-test API, phone camera page and WebSocket streams."""

from __future__ import annotations

import asyncio
import html
import json
import os
from pathlib import Path
from typing import Dict, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from App.field_auth import (
    COOKIE_NAME,
    auth_digest,
    field_auth_enabled,
    password_matches,
    request_authenticated,
    websocket_authenticated,
)
from src.capture.manager import FieldManager


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = Path(os.getenv("CLEAR_DATA_DIR", str(ROOT / "data")))
manager = FieldManager(DATA_DIR)

router = APIRouter(tags=["field"])


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source: Literal["browser", "rtsp"] = "browser"
    rtsp_url: str = ""
    end: Literal["none", "end_a", "end_b"] = "none"


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    source: Optional[Literal["browser", "rtsp"]] = None
    rtsp_url: Optional[str] = None
    court_mode: Optional[Literal["singles", "doubles"]] = None
    calib_method: Optional[Literal["manual", "auto", "segmentation"]] = None
    end: Optional[Literal["none", "end_a", "end_b"]] = None
    overlays: Optional[Dict[str, bool]] = None
    detector: Optional[Dict[str, float]] = None


class MatchRequest(BaseModel):
    camera_a_id: str
    camera_b_id: str


class RecordStart(BaseModel):
    camera_ids: List[str]
    name: str = ""


class CalibrationRequest(BaseModel):
    anchors_px: Dict[str, List[float]]
    method: Literal["manual", "auto", "segmentation"] = "manual"


@router.get("/field", response_class=HTMLResponse)
def field_page() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "field.html").read_text(encoding="utf-8"))


@router.get("/field/login", response_class=HTMLResponse)
def field_login_page(request: Request, next: str = "/field") -> Response:
    return login_page(request, next)


@router.post("/field/login")
def field_login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/field"),
) -> Response:
    return login_submit(request, password, next)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/") -> Response:
    if not field_auth_enabled() or request_authenticated(request):
        return RedirectResponse(_safe_next(next), status_code=303)
    return HTMLResponse(_login_html(next))


@router.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
) -> Response:
    if not field_auth_enabled():
        return RedirectResponse(_safe_next(next), status_code=303)
    if not password_matches(password):
        return HTMLResponse(_login_html(next, error="Wrong password."), status_code=401)
    response = RedirectResponse(_safe_next(next), status_code=303)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0] == "https"
    response.set_cookie(
        COOKIE_NAME,
        auth_digest(),
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=7 * 24 * 3600,
    )
    return response


@router.get("/camera/{token}", response_class=HTMLResponse)
def camera_page(token: str) -> HTMLResponse:
    camera = manager.get_camera_by_token(token)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera link not found.")
    template = (STATIC_DIR / "camera.html").read_text(encoding="utf-8")
    payload = {
        "id": camera["id"],
        "name": camera["name"],
        "token": camera["token"],
        "active": bool(camera.get("active")),
    }
    payload_json = json.dumps(payload).replace("</", "<\\/")
    return HTMLResponse(template.replace("__CAMERA_JSON__", payload_json))


# --------------------------------------------------------------------------- API
@router.get("/api/field/cameras")
def list_cameras() -> Dict[str, object]:
    return {"cameras": manager.list_cameras(), "active_id": manager.active_id, "match_id": manager.match_id}


@router.post("/api/field/cameras")
def create_camera(payload: CameraCreate) -> Dict[str, object]:
    if payload.source == "rtsp" and not payload.rtsp_url.strip():
        raise HTTPException(status_code=400, detail="RTSP URL is required for an RTSP camera.")
    camera = manager.create_camera(payload.name, payload.source, payload.rtsp_url)
    if payload.end and payload.end != "none":
        manager.update_camera(str(camera["id"]), end=payload.end)
    return manager.get_camera(str(camera["id"])) or camera


@router.get("/api/field/cameras/{camera_id}")
def get_camera(camera_id: str) -> Dict[str, object]:
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


@router.patch("/api/field/cameras/{camera_id}")
def update_camera(camera_id: str, payload: CameraUpdate) -> Dict[str, object]:
    changes = payload.model_dump(exclude_none=True)
    if changes.get("source") == "rtsp" and not str(changes.get("rtsp_url", "")).strip():
        current = manager.registry.get(camera_id)
        if current is None or not str(current.get("rtsp_url", "")).strip():
            raise HTTPException(status_code=400, detail="RTSP URL is required for an RTSP camera.")
    camera = manager.update_camera(camera_id, **changes)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


@router.delete("/api/field/cameras/{camera_id}")
def delete_camera(camera_id: str) -> Dict[str, object]:
    if not manager.delete_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found.")
    return {"ok": True, "active_id": manager.active_id}


@router.post("/api/field/cameras/{camera_id}/activate")
def activate_camera(camera_id: str) -> Dict[str, object]:
    camera = manager.activate(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


@router.post("/api/field/deactivate")
def deactivate_camera() -> Dict[str, object]:
    manager.deactivate()
    return {"ok": True, "active_id": None}


@router.get("/api/field/active")
def active_camera() -> Dict[str, object]:
    return {"camera": manager.active_stats(), "active_id": manager.active_id}


@router.post("/api/field/match")
def start_match(payload: MatchRequest) -> Dict[str, object]:
    try:
        match = manager.start_match(payload.camera_a_id, payload.camera_b_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"match": match, "match_id": manager.match_id}


@router.post("/api/field/match/stop")
def stop_match() -> Dict[str, object]:
    manager.stop_match()
    return {"ok": True, "match_id": None}


@router.get("/api/field/match")
def get_match() -> Dict[str, object]:
    return {"match": manager.match_stats(), "match_id": manager.match_id}


@router.get("/api/field/match/fused")
def get_fused() -> Dict[str, object]:
    return {"match_id": manager.match_id, "fused": manager.fused_snapshot()}


# --------------------------------------------------------------------------- recording
@router.post("/api/field/record/start")
def start_recording(payload: RecordStart) -> Dict[str, object]:
    try:
        return manager.start_recording(payload.camera_ids, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/field/record/stop")
def stop_recording() -> Dict[str, object]:
    try:
        return manager.stop_recording()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/field/record")
def recording_status() -> Dict[str, object]:
    return manager.recording_status()


@router.get("/api/field/recordings")
def list_recordings_api() -> Dict[str, object]:
    return {"recordings": manager.list_recordings()}


@router.get("/api/field/recordings/{session_id}")
def get_recording_api(session_id: str) -> Dict[str, object]:
    meta = manager.get_recording(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Recording not found.")
    return {"recording": meta}


@router.get("/api/field/recordings/{session_id}/file/{filename}")
def recording_file(session_id: str, filename: str, dl: bool = False) -> Response:
    if Path(filename).name != filename or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    meta = manager.get_recording(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Recording not found.")
    local = Path(DATA_DIR) / "recordings" / session_id / filename
    if not local.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    headers = {}
    if dl:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(local, media_type="video/mp4", headers=headers)


@router.delete("/api/field/recordings/{session_id}")
def delete_recording_api(session_id: str) -> Dict[str, object]:
    if not manager.delete_recording(session_id):
        raise HTTPException(status_code=404, detail="Recording not found.")
    return {"ok": True}


@router.get("/api/field/cameras/{camera_id}/snapshot.jpg")
def snapshot_jpeg(camera_id: str, raw: bool = False) -> Response:
    jpeg = manager.snapshot_jpeg(camera_id, raw=raw)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="No frame available for this camera.")
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/api/field/cameras/{camera_id}/snapshot")
def save_snapshot(camera_id: str, raw: bool = False) -> Dict[str, object]:
    path = manager.save_snapshot(camera_id, raw=raw)
    if path is None:
        raise HTTPException(status_code=404, detail="No frame available for this camera.")
    return {"ok": True, "path": str(path), "name": path.name}


@router.get("/api/field/cameras/{camera_id}/calibration")
def get_calibration(camera_id: str) -> Dict[str, object]:
    if manager.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return {"calibration": manager.get_calibration(camera_id)}


@router.post("/api/field/cameras/{camera_id}/calibration")
def save_calibration(camera_id: str, payload: CalibrationRequest) -> Dict[str, object]:
    if manager.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    try:
        cal = manager.save_calibration(camera_id, payload.anchors_px, method=payload.method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if cal is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return {
        "ok": True,
        "method": cal.method,
        "anchors_px": {k: list(v) for k, v in cal.anchors_px.items()},
        "reproj_error_cm": round(cal.reproj_error_cm, 2),
    }


@router.post("/api/field/cameras/{camera_id}/calibration/auto")
def auto_calibrate(camera_id: str) -> Dict[str, object]:
    try:
        return manager.auto_calibrate(camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/field/cameras/{camera_id}/calibration/segmentation")
def segmentation_calibrate(camera_id: str) -> Dict[str, object]:
    try:
        return manager.segment_calibrate(camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/field/cameras/{camera_id}/events")
def camera_events(camera_id: str, limit: int = Query(40, ge=1, le=500)) -> Dict[str, object]:
    if manager.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    path = manager.data_dir / "sessions" / camera_id / "events.jsonl"
    if not path.exists():
        return {"events": []}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"events": events}


@router.post("/api/field/cameras/{camera_id}/heartbeat")
def camera_heartbeat(camera_id: str) -> Dict[str, object]:
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    manager.heartbeat(camera_id)
    return {"ok": True, "active": bool(camera.get("active"))}


@router.get("/api/field/health")
def field_health() -> Dict[str, object]:
    return {
        "ok": True,
        "active_id": manager.active_id,
        "match_id": manager.match_id,
        "camera_count": len(manager.registry.list()),
        "auth_enabled": field_auth_enabled(),
    }


# --------------------------------------------------------------------------- websockets
@router.websocket("/ws/field/view/{camera_id}")
async def view_stream(websocket: WebSocket, camera_id: str) -> None:
    if not websocket_authenticated(websocket):
        await websocket.accept()
        await websocket.close(code=1008)
        return
    if manager.get_camera(camera_id) is None:
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await websocket.accept()
    manager.viewer_count(camera_id, 1)
    last_index = -1
    try:
        while True:
            camera = manager.get_camera(camera_id)
            if camera is None:
                await websocket.send_text(json.dumps({"type": "state", "active": False, "missing": True}))
                await asyncio.sleep(0.5)
                continue
            if not camera.get("active"):
                await websocket.send_text(
                    json.dumps({"type": "state", "active": False, "camera": camera})
                )
                await asyncio.sleep(0.5)
                continue

            frame_index = int(camera.get("frame_index") or 0)
            if frame_index != last_index:
                jpeg = manager.snapshot_jpeg(camera_id)
                if jpeg:
                    await websocket.send_bytes(jpeg)
                    last_index = frame_index
            await websocket.send_text(json.dumps({"type": "meta", "camera": camera}))
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError, OSError, Exception):
        pass
    finally:
        manager.viewer_count(camera_id, -1)


@router.websocket("/ws/field/match")
async def match_stream(websocket: WebSocket) -> None:
    if not websocket_authenticated(websocket):
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await websocket.accept()
    last_index = -1
    try:
        while True:
            match = manager.match_stats()
            if match is None:
                await websocket.send_text(json.dumps({"type": "state", "active": False}))
                await asyncio.sleep(0.5)
                continue
            fused = match.get("fused") or {}
            idx = int(fused.get("frame_index") or 0)
            if idx != last_index:
                last_index = idx
                await websocket.send_text(json.dumps({"type": "fused", "match_id": manager.match_id, "fused": fused}))
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError, OSError, Exception):
        pass


@router.websocket("/ws/field/ingest/{camera_id}")
async def ingest_stream(websocket: WebSocket, camera_id: str, token: str = Query("")) -> None:
    if not websocket_authenticated(websocket):
        await websocket.accept()
        await websocket.close(code=1008)
        return
    if not manager.registry.token_matches(camera_id, token):
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await websocket.accept()
    manager.set_ingest_connected(camera_id, True)

    async def status_pusher() -> None:
        try:
            while True:
                camera = manager.get_camera(camera_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "status",
                            "active": bool(camera and camera.get("active")),
                            "online": bool(camera and camera.get("online")),
                        }
                    )
                )
                await asyncio.sleep(2.0)
        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.CancelledError, Exception):
            return

    pusher = asyncio.create_task(status_pusher())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                manager.submit_jpeg(camera_id, message["bytes"])
            elif message.get("text"):
                manager.heartbeat(camera_id)
    except (WebSocketDisconnect, RuntimeError, OSError, Exception):
        pass
    finally:
        pusher.cancel()
        manager.set_ingest_connected(camera_id, False)


# --------------------------------------------------------------------------- auth page
def _safe_next(value: str) -> str:
    parsed = urlparse(value or "/")
    if parsed.scheme or parsed.netloc:
        return "/"
    path = parsed.path or "/"
    allowed = (
        path == "/"
        or path == "/admin"
        or path.startswith("/admin/")
        or path == "/field"
        or path.startswith("/field/")
        or path.startswith("/camera/")
    )
    if allowed:
        return path + (f"?{parsed.query}" if parsed.query else "")
    return "/"


def _login_html(next_path: str, error: str = "") -> str:
    error_html = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CLEAR | Sign in</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Oswald:wght@500;600;700&display=swap');
:root{{--primary:#06483f;--deep:#022f2b;--clay:#f28a24;--ball:#bed95b;--surface:#fff4d8;--text:#f8f2e6;--muted:#9fb5ad;--line:#1d453d;--card:#0d2320;--bg:#041f1b}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(120% 90% at 50% 0%,#0d2320,#022f2b 60%);color:var(--text);font-family:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px}}
.card{{width:min(92vw,400px);background:var(--card);border:1px solid var(--line);border-radius:20px;padding:30px;box-shadow:0 24px 60px rgba(0,0,0,.35)}}
.badge{{display:inline-flex;align-items:center;gap:10px;font-family:'Oswald',sans-serif;font-size:20px;font-weight:600;letter-spacing:.04em}}
.badge .mark{{width:31px;height:31px;border-radius:7px;background:var(--clay);border:2px solid var(--surface);display:grid;place-items:center;position:relative}}
.badge .mark:before{{content:'';position:absolute;inset:4px;border:1px solid var(--surface);opacity:.75;border-radius:3px}}
.badge .mark:after{{content:'';position:absolute;left:4px;right:4px;top:50%;border-top:1px solid var(--surface);opacity:.75}}
h1{{font-family:'Oswald',sans-serif;font-size:30px;text-transform:uppercase;margin:18px 0 6px;letter-spacing:.01em}}
p{{color:var(--muted);font-size:14px;margin:0 0 20px}}
label{{display:block;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:7px}}
input{{width:100%;padding:13px 14px;border-radius:10px;border:1px solid var(--line);background:#0a1b18;color:var(--text);font-size:15px;outline:none;font-family:inherit}}
input:focus{{border-color:var(--ball);box-shadow:0 0 0 3px rgba(190,217,91,.15)}}
button{{width:100%;margin-top:18px;padding:13px;border:0;border-radius:99px;background:var(--ball);color:var(--deep);font-weight:700;font-size:14px;cursor:pointer;font-family:inherit;letter-spacing:.02em}}
button:hover{{background:#c9e26a}}
.err{{color:#f0a08c;margin:0 0 12px;font-size:13px}}
.hint{{margin-top:16px;text-align:center;font-size:11px;color:#6f8a80}}
</style></head><body><form class="card" method="post" action="/login">
<span class="badge"><span class="mark"></span>CLEAR</span>
<h1>Return to court.</h1><p>Enter the studio password to continue.</p>
{error_html}
<input type="hidden" name="next" value="{html.escape(next_path)}"/>
<label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus/>
<button type="submit">Open studio</button>
<div class="hint">Shared access password · set via CLEAR_FIELD_PASSWORD</div>
</form></body></html>"""
