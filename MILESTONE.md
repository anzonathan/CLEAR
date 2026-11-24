# CLEAR — Milestones & Progress

Progress log for the capstone. Milestones are additive; each builds on the last.

- **Milestone 1** — Zero-shot object detection + painted-line/HSV baseline.
- **Milestone 2** — Live field-console app + Coolify deployment.
- **Milestone 3** — Two-camera match mode + recording.
- **Milestone 4** — Web platform: accounts and roles, paired games filmed by two phones, developer tools for live view, calibration, streaming and recorded analysis. *(current)*

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

## Milestone 3 — Two-camera mode + recording

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

## Milestone 4 — Web platform *(current)*

The FastAPI console (`App/`) was a single-operator tool. Milestone 4 moves the same
capture, match and recording engine (`backend/src/capture/`) behind a multi-user web
app: players run games from their own phones, developers analyse them.

### Stack

`proxy` (nginx) → `frontend` (Next.js 14) + `backend` (Django 5, DRF, Channels/Daphne,
PyTorch) + Postgres + Redis. One public entry point; deployed on Coolify behind a
Cloudflare tunnel, with GPU 1 of the server reserved for the backend. See `DEPLOY.md`.

### Roles

| Role | Lands on | Access |
|---|---|---|
| Player | `/app` | Pairing, games, phone camera |
| Developer | `/dev` | Player app + developer tools |
| Admin | `/admin` | Admin dashboard only |

Field console REST endpoints and the live view sockets are developer/admin only;
phones reach the ingest socket with a per-camera token given only to the player who
claimed that end.

### Players: games filmed by two phones

- **Pair** with a six-character code.
- **Start now** or **schedule** a game with a connection (`Game` model, `apps/games/`).
- Each player **claims an end** (End A / End B); claiming creates that game's field camera.
- **Phone camera in the browser** (`components/CameraStreamer.tsx`): rear camera, JPEG
  frames over `/ws/field/ingest/<camera>/`, wake lock.
- **Auto-start:** when both cameras are online and steady for 3 s the game starts by
  itself (idempotent server start under a row lock, so both phones can trigger it). Live
  two-camera analysis and recording begin together.
- **Sound cues:** rising chime + vibration on start, falling tone on end. Silent during
  calibration previews.

### Developers

- **Game analysis** (`/dev`): every game by state. Live view shows both annotated feeds
  plus the fused court (ball, trail, players, speed). Recorded games run the full
  `ClearPipeline` per end in a background thread: in/out/close calls, speeds, strokes,
  ball-tracking coverage, foot and service faults, court charts.
- **Calibration** (`/dev/games/<id>/calibrate/<end>`): a preview mode runs both cameras
  without recording or starting the game; click court points on a still, guided by a
  court map drawn from that camera's viewpoint; auto-detect; reprojection error in cm;
  live overlay check. End A's camera-view point names are converted to absolute court
  names (near/far and left/right swap).
- **Streaming** (`/dev/streaming`): resolution, JPEG quality, frame rate and YOLO input
  size, pushed live to phones. Optional adaptive mode steps down fps → quality →
  resolution on a weak uplink but never below developer-set floors, so the ball stays
  detectable. Shows a ball-size estimate and per-phone measured upload.

### Other

- Landing page at `/`; desktop layout for the player app; notifications via `sonner`.
- GPU: `docker-compose.yml` reserves `CLEAR_GPU_ID` (default 1); `CLEAR_DEVICE=cuda` by
  default with a logged warning on CPU fallback.

```
backend/apps/games/          Game + StreamSettings models, player and developer APIs
backend/apps/games/services.py  claim/release ends, start/stop, preview, analysis thread
backend/websockets/field.py  ingest (settings push, per-camera upload stats), view, match
frontend/app/(app)/app/      player app: games, connections/<id>, games/<id>
frontend/app/dev/            developer tools: games, calibrate, streaming
frontend/components/         CameraStreamer, LiveFeeds, CourtDiagram, GameRow
frontend/lib/anchors.ts      camera-view ↔ absolute court anchor mapping
```

### Experiments

`Docs/platform_experiments.md`: end-to-end two-phone game (21/21 checks), calibration
(15/15), streaming and adaptive quality (14/15; the miss is a test-harness artefact),
ball-size analysis (640 px frames put the ball at ~2 px at the net, under the detector's
~4 px minimum, so defaults moved to 1280/960 px), CPU inference cost.

Bugs found by those runs and fixed:

- WebSocket consumers created their own `FieldManager`, so phone frames never reached the live match.
- Calibration saved during a live game did not apply until restart.
- Leaving one calibration page stopped the preview and let the game start mid-calibration.
- Dropped consumers overwrote upload stats with zeros.

### Known limits / next

- **One live game per server** (in-process runtimes).
- **Calibration is per game**; phones are re-mounted each time.
- **Real-footage measurements still open:** bandwidth (P1), calibration accuracy (P2),
  detectability vs resolution (P3), GPU speed-up (P4). Protocols in `Docs/platform_experiments.md`.
- **Seed accounts** with public passwords are created on every start (`DEPLOY.md` §7).

---

## Tests

`uv run pytest` — **17 passed, 1 failed** (run 2026-11-24). Coverage: match fusion, match
API validation, recording lifecycle, foot faults, pipeline. The failure,
`test_field_password_auth_gate`, checks the retired FastAPI console's login redirect
(`App/`), which Milestone 4 did not modify; it should be removed with `App/`.

The tests import the repository-root `src/`. The deployed backend runs its own copy in
`backend/src/`. The two are identical as of this milestone; keep them in sync, or point
the tests at `backend/src`, until the duplicate is removed.

The web platform itself is covered by the browser end-to-end runs in
`Docs/platform_experiments.md`, not by `pytest`.

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
uv run pytest                                                  # pipeline tests
docker compose --env-file .env.local up -d --build             # local stack on http://localhost:8443
docker compose --env-file .env.local logs -f backend           # backend logs
```

Milestone 2 commands (`uvicorn App.server:app`, `docker-compose.gpu.yml`/`cpu.yml`) refer
to the retired FastAPI console.
