# CLEAR on Coolify

Step-by-step for the Coolify resource. The full reference (architecture, variables, data, security) is in `../DEPLOY.md`.

## 1. Resource

- **Type:** Docker Compose, from `https://github.com/anzonathan/CLEAR`
- **Branch:** `main`
- **Base directory:** `/`
- **Compose file:** `/docker-compose.yml`

Coolify runs only `docker-compose.yml`. It ignores `docker-compose.override.yml`, which holds the local-only ports and the local GPU removal.

## 2. Domain

Attach the domain to the **`proxy`** service only:

```
http://clear.ucu-dct.org:80
```

Leave `postgres`, `redis`, `backend` and `frontend` without a domain. Do not add host port mappings: host port 8000 is Coolify's own dashboard, and 80 and 443 belong to Coolify's Traefik.

## 3. Cloudflare tunnel

The tunnel runs on the host as a systemd service, configured in `/etc/cloudflared/config.yml`. Route the hostname to Traefik on port 80, the same way as the other Coolify apps on this server:

```yaml
  - hostname: clear.ucu-dct.org
    service: http://localhost:80
```

```bash
sudo systemctl restart cloudflared
```

## 4. Environment variables

Minimum for production:

```env
DJANGO_SECRET_KEY=<long random string>
DEBUG=False
ALLOWED_HOSTS=clear.ucu-dct.org,localhost,127.0.0.1,backend
CORS_ALLOWED_ORIGINS=https://clear.ucu-dct.org
CSRF_TRUSTED_ORIGINS=https://clear.ucu-dct.org
CLEAR_DEVICE=cuda
CLEAR_GPU_ID=1
```

Leave `NEXT_PUBLIC_WS_URL` unset. Coolify refuses to delete a variable that the compose file still references, so it must not appear in `docker-compose.yml` either.

All other variables are optional; see `../DEPLOY.md` section 3.

## 5. GPU

The backend reserves host GPU `CLEAR_GPU_ID` (default `1`) through `deploy.resources.reservations.devices` in `docker-compose.yml`. The host needs `nvidia-container-toolkit`. Test it with:

```bash
docker run --rm --gpus device=1 ubuntu nvidia-smi
```

## 6. Options

- **Rolling updates:** off. Run **one replica**, because live camera state is held in the backend process.
- **Storage:** the compose-owned volumes `clear_postgres_data` and `clear-data` persist across deploys.

## 7. After the first deploy

1. Change the seed passwords and delete `user@clear.local` (see `../DEPLOY.md` section 7).
2. Sign in as a developer, open `/dev/streaming` and choose a preset for the court's connection.
3. Run a test game with two phones. Calibrate both ends, and check that the feed stats show `cuda`.
