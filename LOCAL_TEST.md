# CLEAR — Local Test

Run the studio + field console + admin dashboard locally.

## 1. Install

```bash
cd CLEAR
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run

```bash
CLEAR_FIELD_PASSWORD=clearlines python -m uvicorn App.server:app --reload --port 8090
```

Open `http://localhost:8090`.

## 3. Login

- Shared password (no username): **`clearlines`**
- Set via `CLEAR_FIELD_PASSWORD`

## Pages

| Path    | What                              |
|---------|-----------------------------------|
| `/`     | Analytics studio (dashboard)      |
| `/field`| Live field detection console      |
| `/admin`| Club admin dashboard (desktop)    |
| `/login`| Sign-in page                      |

## Auth behaviour

- `CLEAR_FIELD_PASSWORD` unset → open, no login.
- Set → all of `/`, `/admin`, `/field`, `/camera` require the password.

## Notes

- First `/api/state` call generates a synthetic clay rally + runs the pipeline (needs `cv2`, `numpy`; CPU fine).
- Port default `8090`.
