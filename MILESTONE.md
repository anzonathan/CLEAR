# CLEAR — Milestones & Progress

Progress log for the capstone. Milestones are additive; each builds on the last.

- **Milestone 1** — Zero-shot object detection + painted-line/HSV baseline.
- **Milestone 2** — Live field-console app + Coolify deployment.
- **Milestone 3** — Two-camera match mode + recording. *(current)*

---

## Milestone 2 — App + Deployment *(last week)*

The field console turned the offline pipeline into a live, deployable service.

### The app (`/field`)

- **Channels:** phone-browser cameras via `/camera/<token>` and RTSP streams. One
  active channel at a time; activating another stops the previous worker.
- **Detections:** COCO `person` / `sports ball` / `tennis racket` + clay HSV /
  3-frame temporal ball fallback.
- **Court calibration:** per-camera manual 4-corner tap, auto painted-line suggestion,
  optional segmentation via `CLEAR_COURT_SEG_WEIGHTS`.
- **Outputs:** annotated live view, snapshots, per-session JSONL event logs under
  `/data/sessions/`.

```
App/server.py            FastAPI app
App/field_api.py         channel/calibration/snapshot/WS endpoints
App/field_auth.py        shared-password gate
App/static/field.html    console UI
App/static/camera.html   phone camera page
src/capture/manager.py   FieldManager + FieldCameraRuntime
src/capture/registry.py  persistent camera registry
```

### Deployment (Coolify)

- `Dockerfile` — CUDA runtime image, `yolov8n.pt` pre-baked, one-worker uvicorn.
- `docker-compose.yml` + `docker-compose.gpu.yml` / `docker-compose.cpu.yml` overrides.
- `CLEAR_DEVICE`, `CLEAR_YOLO_IMGSZ`, `CLEAR_FIELD_TARGET_FPS` tune the CPU fallback.
- `/data` mounted as a persistent volume.

---

## Milestone 3 — Two-camera mode + recording *(current)*

### Two-camera match mode

Two phones on opposite ends, each close to its own half, feed one shared
court-coordinate track. Close-up framing raises ball pixel density — the exact thing
single-camera struggled with.

- Two `FieldCameraRuntime`s run at once (previously one at a time).
- Each camera calibrates to the same ITF court plane via its own homography.
- New `CourtBallTracker` Kalman filter tracks the ball in **court metres**, not pixels.
- `PlayerTracker` stays shared: P1 (near, `y > net`) / P2 (far, `y < net`) are
  camera-agnostic because homography projects feet into one coordinate frame.
- Ball confidence weighted by pixel radius — the camera seeing the ball bigger wins.
- Fused ball + both players projected back into each camera view for the overlay.

```
src/track/match_fuser.py   CourtBallTracker, MatchFuser, project_fused_to_image
src/capture/manager.py     MatchRuntime (two runtimes + fusion loop)
src/capture/registry.py    camera "end" role (end_a / end_b)
App/field_api.py           match endpoints + /ws/field/match
App/static/field.html      match modal + top-down court radar
```

### Recording

Record two feeds from the console, then view and download.

- Writes **raw** and **annotated** MP4s per camera.
- Stored locally under `CLEAR_DATA_DIR/recordings/` (Coolify volume — persists).
- Seekable in-browser playback, one-click download, delete when done.

```
src/capture/recorder.py   CameraRecorder, RecordingSession
App/field_api.py           record + recordings endpoints
```

---

## Tests

`pytest` — **15 passing**. Coverage: match fusion, match API validation, recording
lifecycle (MP4 written, listed, deleted).

---

## Known limits / next

- **Time sync:** two phones not hardware-synced → fused ball speed jitter (Kalman smooths).
- **Calibration dependency:** match mode needs both cams calibrated to same orientation.
- **Load:** two inference workers double GPU/CPU cost.

Next: bounce/line-calling on the fused track, tune `CourtBallTracker` gate/noise on real
two-phone footage, wire recordings into the Analytics Studio.

---

## Useful commands

```bash
uv run pytest                                            # tests
uv run uvicorn App.server:app --host 0.0.0.0 --port 8090 # local server
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d  # GPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d  # CPU
```
