# Deploying CLEAR

Production reference for the CLEAR web platform at `https://clear.ucu-dct.org`. For Coolify-specific clicks, see `deploy/coolify.md`. For running on your own machine, see `LOCAL_TEST.md`.

> The FastAPI field console in `App/` (`/field`, `/camera/<token>`, port 8090) is the Milestone 2 prototype and is **no longer deployed**. Its camera, match and recording engine (`backend/src/capture/`) now runs inside the Django backend.

## 1. Architecture

```
phone / browser ──https──> Cloudflare tunnel ──> host :80 (Coolify Traefik)
                                                   │
                                                   ▼
                                     proxy (nginx :80)  ── only public entry point
                                      │                         │
                    /  (pages, Next.js rewrites)      /api/ /ws/ /django-admin/ /static/ /media/
                                      ▼                         ▼
                             frontend (Next.js :3000) ──> backend (Django + Channels on Daphne :8000)
                                                                 │        │         │
                                                            postgres    redis    /data volume
                                                                                 (cameras, calibrations,
                                                                                  recordings, analysis)
```

| Service | Image / build | Role |
|---|---|---|
| `proxy` | `proxy/` (nginx 1.27) | Single entry point; routes pages to the frontend, API and WebSockets to the backend |
| `frontend` | `frontend/` (Next.js 14 standalone) | Landing page, player app, developer tools, admin dashboard |
| `backend` | `backend/` (Django 5, DRF, Channels, PyTorch) | Auth, pairing, games, phone ingest, live detection, recording, offline analysis |
| `postgres` | `postgres:16-alpine` | Users, connections, games, stream settings |
| `redis` | `redis:7-alpine` | Channels layer |

**Run one backend replica only.** Live camera runtimes, the match fuser, recorders and per-phone streaming stats live in the backend process. This has two consequences:

- Two replicas would split the phones between processes.
- Only one game can be live at a time.

## 2. Host prerequisites

The server (`dct1`) has two NVIDIA RTX A4000 cards with driver 595.91 and CUDA 13.2. The backend image ships `torch 2.15.0+cu132`, which matches.

1. Check that Docker can reach the GPU:

   ```bash
   docker run --rm --gpus device=1 ubuntu nvidia-smi
   ```

2. If that fails with `could not select device driver "nvidia"`, install `nvidia-container-toolkit` and register it with Docker:

   ```bash
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

### GPU

`docker-compose.yml` reserves one GPU for the backend:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ["${CLEAR_GPU_ID:-1}"]
          capabilities: [gpu]
```

- **Card:** the default is host GPU **1**, because GPU 0 is mostly taken by another workload (15.1 of 16 GB in use when checked). Inside the container the reserved card appears as `cuda:0`.
- **Device setting:** `CLEAR_DEVICE` defaults to `cuda`.
- **No GPU:** if CUDA is unavailable, the backend logs `[CLEAR] WARNING: CLEAR_DEVICE=cuda but CUDA is not available; running on CPU.` and carries on, about 10× slower.
- **Check it:** open a live game in `/dev`. The feed stats should show `cuda`, not `cpu`.

## 3. Environment variables

Set these in Coolify, or in `.env` for plain Docker Compose.

| Variable | Default | Production value / notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | **Set a long random value** |
| `DEBUG` | `True` | **Set `False`.** This also makes session and CSRF cookies `Secure` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,backend` | `clear.ucu-dct.org,localhost,127.0.0.1,backend` (keep `backend`: the frontend calls it internally) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:8443` | `https://clear.ucu-dct.org` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8443` | `https://clear.ucu-dct.org` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | empty | Google sign-in, optional |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | console backend | SMTP for account emails. Without it, emails go to the backend log |
| `CLEAR_DEVICE` | `cuda` | `cpu` to force CPU |
| `CLEAR_GPU_ID` | `1` | Host GPU index to reserve |
| `CLEAR_DETECTOR_MODE` | `hybrid` | `hybrid`, `yolo` or `classical` |
| `CLEAR_YOLO_IMGSZ` | `640` | Overridden by **Detector input** in `/dev/streaming` from the next game start |
| `CLEAR_FIELD_TARGET_FPS` | `15` | Frame rate the recorder writes MP4s at |
| `CLEAR_COURT_SEG_WEIGHTS` | empty | Optional court-segmentation weights for calibration |

Do **not** set `NEXT_PUBLIC_WS_URL`. WebSockets use the page's own host, and the proxy routes `/ws/` to the backend.

Phone encoding (resolution, quality, frame rate, adaptive floors) is **not** an environment variable. Developers set it in `/dev/streaming`, and it is stored in the database.

## 4. Routing

- **Coolify domain:** attach `http://clear.ucu-dct.org:80` to the **`proxy`** service only. The other services get no domain.
- **Host ports:** none are published in `docker-compose.yml`. Coolify's own dashboard uses host port 8000, and its Traefik proxy uses 80 and 443.
- **Cloudflare tunnel:** the tunnel runs on the host as a systemd service, configured in `/etc/cloudflared/config.yml`. It sends the hostname to Traefik on port 80, like the other Coolify apps:

  ```yaml
  - hostname: clear.ucu-dct.org
    service: http://localhost:80
  ```

  Then run `sudo systemctl restart cloudflared`.

WebSockets (`/ws/field/ingest/…`, `/ws/field/view/…`, `/ws/field/match/`) pass through Cloudflare and Traefik unchanged.

## 5. Persistent data

| Where | What |
|---|---|
| Volume `clear_postgres_data` | Database |
| Volume `clear-data` at `/data` | Camera registry, calibrations, recordings and analysis output (layout below) |
| Bind `./backend/media` at `/app/media` | Uploaded files |

Layout of `/data`:

```
cameras.json                          camera registry (one camera per player per game end)
cameras/<camera_id>/calib.json        calibration
sessions/<camera_id>/                 snapshots, detection event logs
recordings/<rec_id>/meta.json         recording index
recordings/<rec_id>/<camera_id>_raw.mp4    raw feed (input to analysis)
recordings/<rec_id>/<camera_id>_annot.mp4  annotated feed
recordings/<rec_id>/<camera_id>_*_web.mp4  H.264 copy for browser playback (made on first preview)
analysis/<game_id>/<camera_id>/       summary.json, bounces.json, tracks.csv, court_analytics.png, annotated_rally.mp4
analysis/<game_id>/<camera_id>/segments/<segment_id>/   same files, for one developer-marked segment
```

Recordings grow at roughly the upload rate of both phones. Clean old ones out periodically.

**Recording preview.** Recordings are written as `mp4v`, which browsers cannot play. The first time a developer
opens a recording in **Dev tools → Games → *game* → Recording preview**, the backend converts it once with
`ffmpeg`, which is installed in the backend image, and keeps the `*_web.mp4` copy next to the original. That copy
is roughly the same size as the original or smaller. Conversion runs in the background, and the page polls until
it is ready. Deleting a `*_web.mp4` is safe: it is rebuilt on the next preview. Set `FFMPEG_BIN` to use a
different ffmpeg binary.

**Data export.** *Export selected* / *Export all* on that page downloads a ZIP (`manifest.json`, `runs.csv`, and
per run `summary.json`, `bounces.csv`, `tracks.csv`, `faults.csv`) for `notebooks/post_analysis.ipynb`.

## 6. Deploy

1. Push to `main`.
2. Redeploy in Coolify.
3. On start, the backend applies migrations (`migrate`), runs `seed_users`, then starts Daphne.

Check the deploy:

```bash
curl -fsS https://clear.ucu-dct.org/api/field/health/    # {"ok": true, ...}
```

Then:

1. Sign in.
2. Open `/dev`.
3. Start a test game with two phones.
4. Confirm both feeds and the `cuda` device in the feed stats.

## 7. Security

- **Seed accounts.** `backend/entrypoint.sh` runs `seed_users` on every start. It creates `admin@clear.local` / `admin123` (Django superuser), `dev@clear.local` / `dev123` and `user@clear.local` / `user123` if they are missing. The passwords are public in this repository.
  - After the first deploy, change them: `python manage.py changepassword admin@clear.local` in the backend container terminal, and the same for the dev account.
  - Delete `user@clear.local`.
  - Changed passwords survive restarts. Deleted accounts come back on the next start.
- **`DEBUG` defaults to `True`** in `docker-compose.yml`. Production must set `DEBUG=False`.
- **Database password.** The Postgres password is fixed in `docker-compose.yml`. The database is not published to the host, but change the password if the server is shared.
- **Field console access.** The field console API and the live view sockets are restricted to developers and admins. Phones authenticate to the ingest socket with a per-camera token, which only the player who claimed that end receives.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Deploy fails: `Bind for 0.0.0.0:8000 failed: port is already allocated` | A host port published in compose | Keep host ports out of `docker-compose.yml`; local ports belong in `docker-compose.override.yml` |
| Deploy fails: `could not select device driver "nvidia"` | No NVIDIA container runtime | Install `nvidia-container-toolkit` (section 2) |
| Site returns Cloudflare 502 | Tunnel points at a port nothing listens on | Tunnel to `http://localhost:80`; domain on `proxy` port 80 |
| Login returns `Unexpected token 'I'… is not valid JSON` | Backend down, or frontend built with the wrong `BACKEND_URL` | Check backend logs; `BACKEND_URL` is a build argument (`http://backend:8000`) |
| `CSRF Failed` on any form | Origin not trusted | Add the exact `https://` origin to `CSRF_TRUSTED_ORIGINS` and `CORS_ALLOWED_ORIGINS` |
| Feed stats show `cpu` | GPU not reserved or not visible | Section 2; check `CLEAR_DEVICE` and the backend log warning |
| `/dev/streaming` shows no phones while games run | Phones not streaming, or a second backend replica | Check the phone shows **Live**; run one replica only |
