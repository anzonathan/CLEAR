# CLEAR: running locally

Runs the full stack on your machine with Docker: Postgres, Redis, the Django backend, the Next.js frontend, and the nginx proxy in front of them. Detection runs on the CPU locally.

## 1. Prerequisites

- Docker Desktop, running.
- About 8 GB free disk space. The backend image includes PyTorch.

## 2. Configure

Local settings live in `.env.local`, which is git-ignored. The production `.env` is never used locally. Create `.env.local`:

```env
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,backend
CORS_ALLOWED_ORIGINS=http://localhost:8443
CSRF_TRUSTED_ORIGINS=http://localhost:8443
CLEAR_DEVICE=cpu
```

## 3. Start

```bash
docker compose --env-file .env.local up -d --build
```

`docker-compose.override.yml` is picked up automatically. Locally it:

- publishes the proxy on **http://localhost:8443** and the backend on port 8000,
- removes the GPU reservation, since Macs and most laptops have no NVIDIA GPU.

Coolify does not use this file.

On start, the backend applies migrations and creates the seed accounts.

Watch the logs with:

```bash
docker compose logs -f backend
```

## 4. Sign in

| Email | Password | Role |
|---|---|---|
| `admin@clear.local` | `admin123` | admin |
| `dev@clear.local` | `dev123` | developer |
| `user@clear.local` | `user123` | player |

These accounts are created on **every** environment, production included. See the security note in `DEPLOY.md`.

## 5. Pages

| Path | What |
|---|---|
| `/` | Landing page |
| `/login`, `/register` | Sign in, create an account |
| `/app` | Player app: home, games, pair, connections, profile |
| `/app/connections/<id>` | Start or schedule a game with a partner |
| `/app/games/<id>` | Pick an end, phone camera, game status |
| `/dev` | Developer: game analysis, live view, recorded analysis |
| `/dev/games/<id>/calibrate/<end_a\|end_b>` | Developer: camera calibration |
| `/dev/streaming` | Developer: streaming settings and live upload rates |
| `/admin` | Admin dashboard |
| `/django-admin/` | Django admin (maintenance) |

How to use each one: `Docs/USAGE.md`.

## 6. Testing the phone camera locally

Browsers only allow the camera on `https://` or `localhost`.

- **On the same computer:** open two browser windows on `http://localhost:8443`, signed in as two paired players. Each can use the laptop webcam.
- **From a real phone:** expose the local proxy over HTTPS, for example with a Cloudflare quick tunnel: `cloudflared tunnel --url http://localhost:8443`. Add the tunnel's hostname to `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` in `.env.local`, then restart the stack.

## 7. Automated checks

Unit tests for the vision pipeline:

```bash
uv run pytest
```

The end-to-end checks (two simulated phones, calibration, streaming) are browser scripts built on Playwright. They drive Chrome's fake camera through the real stack on `localhost:8443`. What they cover and the results are in `Docs/platform_experiments.md`.

## 8. Rebuilding after changes

```bash
docker compose --env-file .env.local up -d --build backend frontend proxy
```

- **Frontend:** `BACKEND_URL` and every `NEXT_PUBLIC_*` value are fixed when the frontend image is built. Changing them needs a rebuild, not a restart.
- **New models:** create the migration inside a throwaway backend container with the source mounted:

  ```bash
  docker compose --env-file .env.local run --rm --no-deps -v "$PWD/backend:/app" \
    --entrypoint python backend manage.py makemigrations
  ```

## 9. Reset

```bash
docker compose down -v
```

This deletes the local database, recordings and calibrations.
