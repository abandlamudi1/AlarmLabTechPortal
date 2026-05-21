# Changelog — 2026-05-12 — Stephen Nodder

## Sprint 2 Stream B: Slice G-part1 — Docker / WSGI / CI

### What shipped
- **wsgi.py** (NEW, issue #5): WSGI entry point for Gunicorn; exposes `app` from `app.py`.
- **entrypoint.sh** (NEW, issue #22): Container startup script — ensures data directories exist, initialises the app context, then hands off to Gunicorn. All settings (PORT, GUNICORN_WORKERS, GUNICORN_TIMEOUT) are env-var-driven.
- **requirements-prod.txt** (NEW, issue #5): Production-only dep — `gunicorn==22.0.0`. Kept separate from `requirements.txt` to avoid conflicts with Stream A and keep the dev loop lightweight.
- **Dockerfile** (NEW, issue #19): Multi-stage build (`builder → base → web / worker / beat`). `python:3.12-slim` base; `DATA_DIR=/data` with four sub-directories; non-root `appuser`; image size <300 MB (292 MB measured). `worker` and `beat` targets ship as topology stubs only — Slice C (Sprint 3) activates Celery.
- **docker-compose.yml** (NEW, issue #20): Full-stack compose — `web`, `worker`, `beat`, `redis`. Named volumes for `db-data`, `upload-data`, `generated-data`, `redis-data`. Health checks on `web` and `redis`. `.env` loaded by all services.
- **docker-compose.dev.yml** (NEW, issue #23): Dev overlay — mounts source `.:/app` for hot-reload, switches web command to `flask run --reload`, sets `FLASK_ENV=development` / `FLASK_DEBUG=1`.
- **.github/workflows/ci.yml** (NEW, issue #25): GitHub Actions CI — triggers on push to master and PRs; builds all three targets; starts compose stack; waits for health; runs pytest; smoke-tests GET /; tears down. Docker layer caching enabled.

### Technical decisions
- **Builder stage** in Dockerfile strips test-only packages (pytest, pluggy, pygments, rich, markdown-it-py, mdurl) from the runtime image to stay under 300 MB without modifying `requirements.txt`.
- **HEALTHCHECK** points at `/` instead of `/healthz` because the `/healthz` endpoint lands in Slice B (Sprint 3). A `TODO(Slice-B)` comment is present in both Dockerfile and docker-compose.yml.
- **Celery worker/beat** are topology stubs only — they run a sleep-forever no-op. The actual `celery_app.py` and task modules land in Slice C. A `TODO(Slice-C)` comment documents the activation point.
- `requirements-prod.txt` isolates Gunicorn (and any future prod-only deps) from the dev requirements, following the Slice G-part1 soft-edge guidance.

### Issues closed
#5, #19, #20, #22, #23, #25 — all closed via PR on merge.

### Blockers / follow-ups
- None. Slice C will activate Celery; Slice B will add `/healthz`.
