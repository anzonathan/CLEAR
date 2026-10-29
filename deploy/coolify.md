# Deploy CLEAR field console on Coolify

## 1. Host prerequisites (Dell Precision 5820)

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If the second command fails (`could not select device driver "nvidia" with capabilities: [[gpu]]`), install the NVIDIA driver and `nvidia-container-toolkit`, then set `nvidia` as Docker's default runtime:

```bash
sudo nvidia-ctk runtime configure --runtime=docker --set-as-default
sudo systemctl restart docker
```

`docker-compose.yml` uses `CLEAR_DEVICE=auto` and `NVIDIA_VISIBLE_DEVICES=all` without a hard device reservation, so Coolify can still start the container on CPU if the NVIDIA runtime is not installed yet.

## 2. Coolify application

- Project: `CLEAR`
- Resource: **Docker Compose** from `https://github.com/anzonathan/CLEAR`
- Branch: `main`
- Base directory: `/` (the repository root containing `docker-compose.yml`)
- Compose file: `/docker-compose.yml`
- Port: `8090` (published on host `8090:8090` so it never conflicts with Coolify on `8000`)
- Ingress / Tunnel target: `http://localhost:8090` (or Coolify domain -> service `clear-field`, port `8090`)
- Do not enable rolling updates. One replica only.
- Persistent storage: compose-owned named volume `clear-data` mounted at `/data`.

## 3. Environment variables

| Variable | Default | Notes |
|---|---|---|
| `CLEAR_FIELD_PASSWORD` | empty | Set this. Protects `/field`, `/camera/*`, field APIs and WebSockets. |
| `CLEAR_DEVICE` | `cuda` | Use `cpu` if the GPU is unavailable. |
| `CLEAR_YOLO_IMGSZ` | `640` | 480 on CPU / low VRAM. |
| `CLEAR_FIELD_TARGET_FPS` | `15` | Increase on a strong GPU. |
| `CLEAR_FIELD_JPEG_QUALITY` | `72` | Lower to save bandwidth. |
| `CLEAR_FIELD_MAX_WIDTH` | `960` | Inference + stream width cap. |
| `CLEAR_RESULTS_DIR` | `/data/results` | Legacy studio artefacts. |
| `CLEAR_CALIB_PATH` | `/data/calib/session.json` | Legacy single-camera calibration. |
| `CLEAR_COURT_SEG_WEIGHTS` | empty | Optional court segmentation weights inside the container. |
| `CLEAR_DETECTOR_MODE` | `hybrid` | `hybrid`, `yolo` or `classical`. |

`CLEAR_YOLO_WEIGHTS` is fixed to `/app/models/yolov8n.pt`; the image bakes the COCO weights at build time.

## 4. Cloudflare Tunnel / Ingress

Point your ingress / tunnel hostname (`clear.<your-subdomain>`) to `http://localhost:8090` (or `http://127.0.0.1:8090`). Keep WebSockets enabled. Cloudflare supports the long-lived camera ingest/view sockets, but make sure no proxy rule buffers `text/event-stream` or WebSocket traffic.

## 5. Phone camera

1. Open `https://clear.<subdomain>/field`.
2. Add a **Phone browser** channel.
3. Copy the generated `/camera/<token>` link to a phone on the same tunnel.
4. Open the link, tap **Start camera**, allow camera access.
5. Activate the channel in the console. The phone switches from standby to sending frames.

Only the active channel is decoded and inferred. Switching channels stops the previous worker and asks the old phone page to pause sending.

## 6. Calibration

Per camera:

- **Manual 4 corners**: tap far-left, far-right, near-right, near-left.
- **Auto lines**: painted-line suggestion. Verify the overlay.
- **Segmentation**: requires `CLEAR_COURT_SEG_WEIGHTS`; no model is bundled.

## 7. Health and logs

```bash
curl https://clear.<subdomain>/api/health
curl https://clear.<subdomain>/api/field/cameras
```

Coolify runtime logs show Uvicorn. Field snapshots and event logs are under `/data/sessions/<camera_id>/`.

## 8. Local test

```bash
uv run uvicorn App.server:app --host 0.0.0.0 --port 8090
# or
docker compose up --build
```

Open `http://localhost:8090/field`.

## Notes / limits

- `yolov8n.pt` is zero-shot COCO. Racket and ball detection will be weak on small/fast objects. This build is for field testing the capture/stream/overlay loop, not final accuracy.
- Court "detection" is calibration, not a learned class. Segmentation needs trained weights.
- Phone camera requires HTTPS and the tab to stay open/unlocked.
- Snapshots + JSONL events are always on. Annotated MP4 recording is not implemented yet.
