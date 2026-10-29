# CLEAR Deployment Guide (`DEPLOY.md`)

Deployment reference for **CLEAR: Clay-court Line Evaluation and Automated Refereeing** — covering the live **Field Detection Console** (`/field`), **Phone Camera Node** (`/camera/<token>`), and **Analytics Studio** (`/`).

---

## 1. Architecture Overview

| Component | Path | Purpose |
|---|---|---|
| **Analytics Studio** | `/` | Post-point review, virtual court homography, synthetic/uploaded rally pipeline, IN/OUT line judge |
| **Field Detection Console** | `/field` | Live single-active-channel console for player, racket, ball, and court overlays |
| **Field Sign-In** | `/field/login` | Shared-password authentication gate (active when `CLEAR_FIELD_PASSWORD` is set) |
| **Phone Camera Node** | `/camera/<token>` | Mobile browser WebRTC capture page pushing JPEG frames over WebSocket (`/ws/field/ingest/<id>`) |
| **Health Check (Public)** | `/api/health` | Container health endpoint (`{"ok": true, "service": "clear", "field_ready": true}`) |
| **Field Health Check** | `/api/field/health` | Field console state (`active_id`, `camera_count`, `auth_enabled`) |

**Key runtime constraint:** Run **1 worker (`--workers 1`) and 1 container replica only**. Active camera state, frame buffers, and WebSocket viewers live in-process. Only **one camera channel** is decoded and inferred at a time; switching channels stops the previous worker.

---

## 2. Pre-Deployment Verification Checklist

Run these checks locally before pushing or deploying:

```bash
# 1. Run full unit + integration + WebSocket test suite
.venv/bin/pytest -v

# 2. Validate Docker Compose manifests (GPU default + CPU override)
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml -f docker-compose.cpu.yml config

# 3. Smoke-test Uvicorn production command locally
.venv/bin/uvicorn App.server:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips "*"
```

Verify health endpoints:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/field/health
```

---

## 3. Host Prerequisites (GPU Server / Dell Precision 5820)

Verify NVIDIA drivers and Docker GPU runtime on the host machine:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If Docker cannot access the GPU, install and configure `nvidia-container-toolkit`:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## 4. Coolify Deployment (Recommended Production Setup)

### 4.1 Create Coolify Resource

1. In Coolify, create a **Docker Compose** resource from `https://github.com/anzonathan/CLEAR`.
2. Set configuration:
   - **Branch:** `main`
   - **Base Directory:** `/`
   - **Docker Compose Location:** `/docker-compose.yml`
   - **Service:** `clear-field`
   - **Internal Port:** `8000`
   - **Domain:** `https://clear.<your-domain>`
3. **Important:** Keep replicas at `1` and disable rolling updates so two containers do not compete for the same camera stream.
4. **Host port note:** `docker-compose.yml` exposes port `8000` internally on the Coolify Docker network and intentionally does **not** bind host port `8000` (avoiding conflict with Coolify's own dashboard on host port `8000`).

### 4.2 Environment Variables

Configure these in Coolify (see `deploy/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `CLEAR_FIELD_PASSWORD` | *(empty)* | **Set in production.** Protects `/field`, `/camera/*`, `/api/field/*`, and `/ws/field/*` |
| `CLEAR_DEVICE` | `cuda` | Inference device (`cuda`, `cpu`, or `auto`) |
| `CLEAR_YOLO_IMGSZ` | `640` | YOLO input image size (`640` on GPU, `480` on CPU) |
| `CLEAR_FIELD_TARGET_FPS` | `15` | Target inference FPS cap (`15` on GPU, `8` on CPU) |
| `CLEAR_FIELD_JPEG_QUALITY` | `72` | Annotated stream JPEG quality (`1`–`100`) |
| `CLEAR_FIELD_MAX_WIDTH` | `960` | Max frame width before inference/streaming |
| `CLEAR_DETECTOR_MODE` | `hybrid` | `hybrid` (YOLO + clay HSV/3-frame temporal), `yolo`, or `classical` |
| `CLEAR_COURT_SEG_WEIGHTS` | *(empty)* | Optional path to custom court segmentation `.pt` weights inside container |
| `CLEAR_DATA_DIR` | `/data` | Persistent storage root inside container |
| `CLEAR_RESULTS_DIR` | `/data/results` | Output directory for Analytics Studio runs |
| `CLEAR_CALIB_PATH` | `/data/calib/session.json` | Studio default calibration file path |
| `CLEAR_YOLO_WEIGHTS` | `/app/models/yolov8n.pt` | Pre-baked COCO weights inside container image |

### 4.3 Cloudflare Tunnel & Reverse Proxy Notes

- Point your Cloudflare Tunnel public hostname (`clear.<your-domain>`) to the Coolify proxy (`http://localhost:80` or Traefik).
- **HTTPS is mandatory** for phone cameras (`navigator.mediaDevices.getUserMedia` requires a secure context).
- Ensure **WebSockets** are enabled in Cloudflare (`Network -> WebSockets -> ON`) and no proxy rule buffers `/ws/field/*`.

---

## 5. Standalone Docker Compose Deployment (Without Coolify)

### 5.1 GPU Host

```bash
cp deploy/.env.example .env
docker compose up -d --build
```

*(If running without Coolify's reverse proxy and you need host port access, run with `-p 8000:8000` or add a `ports: ["8000:8000"]` override).*

### 5.2 CPU-Only Host / Laptop Fallback

Use `docker-compose.cpu.yml` to strip the NVIDIA GPU reservation and lower image size/FPS defaults:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

---

## 6. Persistent Storage Layout (`/data`)

The named Docker volume `clear-data` is mounted at `/data`:

```text
/data/
  cameras.json                         # Registered camera channels, tokens, thresholds, overlay settings
  cameras/
    <camera_id>/
      calib.json                       # Per-camera homography matrix + 4-corner anchors
  sessions/
    <camera_id>/
      events.jsonl                     # Timestamped activate/deactivate/detection/snapshot telemetry
      snapshots/
        YYYYMMDD_HHMMSS_mmm.jpg        # Saved annotated snapshots
        YYYYMMDD_HHMMSS_mmm_raw.jpg    # Saved raw snapshots
  calib/
    session.json                       # Analytics Studio calibration
  results/
    rally1/                            # Analytics Studio processed rally video + metrics
```

---

## 7. Field Operations Workflow

### 7.1 Connect a Phone Camera

1. Open `https://clear.<your-domain>/field` and sign in if `CLEAR_FIELD_PASSWORD` is enabled.
2. Click **+ Add**, choose **Phone browser**, enter a court name (e.g. `UCU Court 1`), and click **Create channel**.
3. Copy the generated `/camera/<token>` URL and open it on the tripod phone over HTTPS.
4. On the phone, sign in if prompted, tap **Start camera**, and allow rear camera access. Keep the phone tab in the foreground and screen unlocked.
5. In `/field`, click **Activate** on that channel. The phone transitions from `Standby` to `Live` and streams frames to the server.

### 7.2 Connect an RTSP Camera

1. Click **+ Add**, choose **RTSP stream**, and provide `rtsp://user:pass@host:554/stream`.
2. Click **Activate** to start pulling and inferring the RTSP stream via FFmpeg.

### 7.3 Calibrate the Court

With a channel active and streaming video, click **Calibrate**:
- **Manual 4 corners:** Tap court corners in clockwise order starting top-left: `far-left`, `far-right`, `near-right`, `near-left`, then click **Save 4-corner calibration**.
- **Auto lines:** Runs Canny/Hough painted-line quad detection and applies suggested corners.
- **Segmentation:** Uses `CLEAR_COURT_SEG_WEIGHTS` if configured.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Phone says `Camera requires HTTPS` | Opened via plain `http://<ip>` | Access `/camera/<token>` via `https://` domain or Cloudflare Tunnel |
| Phone stays in `Standby` | Channel not activated in `/field` | Click **Activate** on the channel card in `/field` |
| Phone link says `Camera link rejected` | Password changed or invalid token | Re-authenticate at `/field/login` and re-copy the phone link from `/field` |
| `Auto lines` fails to find court | Worn clay lines or no frame yet | Wait for live video frame, or use **Manual 4 corners** |
| Low FPS / high inference latency | Running on CPU or high resolution | Verify `CLEAR_DEVICE=cuda` & `nvidia-smi`, or lower `CLEAR_YOLO_IMGSZ=480` and `CLEAR_FIELD_TARGET_FPS=8` |
