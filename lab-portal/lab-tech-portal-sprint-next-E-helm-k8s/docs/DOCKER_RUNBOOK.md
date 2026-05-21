# Docker Operations Runbook

This guide covers running the Lab Tech Portal in Docker via docker-compose.

> **Status:** Docker artifacts (`Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`) shipped in [Slice G-part1 / PR #58](https://github.com/adc-quality/lab-tech-portal/pull/58), which has merged. All commands below are operational.

## Prerequisites

- **Git** — to clone the repository
- **Docker 24+** and **Docker Compose v2** (ships with Docker Desktop; verify with `docker compose version`)
- **Repository cloned and working directory set:**
  ```bash
  git clone https://github.com/adc-quality/lab-tech-portal.git
  cd lab-tech-portal
  ```
- **`.env` file created** — copy the example and fill in your secrets:
  ```bash
  cp .env.example .env
  ```
  See the [Environment Variables](#environment-variables) section for what to fill in.

---

## Quick Start

### Production stack

```bash
# Run from the repo root (lab-tech-portal/)
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY to a cryptographically random value:
#   python -c 'import secrets; print(secrets.token_urlsafe(64))'
docker compose up -d
# Web UI available at http://localhost:8000
# Logs: docker compose logs -f web
# Stop: docker compose down
```

Data persists across restarts in named Docker volumes (`db-data`, `upload-data`, `generated-data`, `redis-data`).

### Development (hot-reload)

```bash
# Run from the repo root (lab-tech-portal/)
cp .env.example .env   # skip if already done
docker compose -f docker-compose.yml -f docker-compose.dev.yml up web redis
# Edit source files — Flask reloads automatically (no rebuild needed)
```

---

## Service Management

### Start all services

```bash
# Run from the repo root (lab-tech-portal/)
docker compose up -d
```

Starts `web`, `redis`, and `prometheus` in the background.

> **Note:** `worker` and `beat` are profile-gated and do **not** start with the plain `docker compose up -d` command.
> To start them, use: `docker compose --profile worker up -d`
> They are non-functional stubs until Slice C (Sprint 3).

### Stop services

```bash
docker compose down
```

Stops all containers. Data volumes are preserved.

### Restart a specific service

```bash
docker compose restart web   # Restart just the web service
docker compose restart redis  # Restart just redis (clears in-memory cache)
```

### View service status

```bash
docker compose ps
```

### Remove all containers and images

```bash
docker compose down --volumes --rmi all
```

**Warning:** This deletes all data volumes. Use only when resetting your environment.

---

## Logs and Debugging

### View logs for all services

```bash
docker compose logs --tail=50 -f
```

### View logs for a specific service

```bash
docker compose logs -f web     # Flask/Gunicorn logs
docker compose logs -f worker  # Celery worker logs (stub mode)
docker compose logs -f redis   # Redis logs
```

### Check service health

```bash
# Run from the repo root (lab-tech-portal/)
docker compose ps
# Look at the STATUS column — should show "healthy" or "Up X seconds"
```

### Open a shell in the web container

```bash
# Run from the repo root (lab-tech-portal/)
docker compose exec web bash
```

From there you can run `flask shell`, inspect `/data` volumes, or run `python -m pytest`.

---

## Environment Variables

Environment variables are loaded from `.env` via the `env_file` directive in `docker-compose.yml`.

### Key variables

- **`SECRET_KEY`** (REQUIRED in production): Flask session encryption key. Must be a random string — never the default `change-me`.
  Generate with: `python -c 'import secrets; print(secrets.token_urlsafe(64))'`
- **`FLASK_ENV`**: `development` or `production`. The `.env.example` default is `development`; `docker-compose.yml` falls back to `production` only if `FLASK_ENV` is unset in the environment.
- **`GUNICORN_WORKERS`**: Number of Gunicorn worker processes (default: 4)
- **`PORT`**: Listen port for the web service (default: 8000)
- **`JIRA_URL`** / **`JIRA_PAT`**: Jira base URL and personal access token; required if using Lab Request / Print Request Jira integration
- **`OKTA_CLIENT_ID`** / **`OKTA_CLIENT_SECRET`** / **`OKTA_ISSUER`** / **`OKTA_REDIRECT_URI`**: All four must be set together, or all left blank. If blank, the app sets `LOGIN_DISABLED=True` (via `app.py`), which disables all auth checks. Use only for local development — never for production-like environments.
- **`REDIS_URL`** / **`CELERY_BROKER_URL`** / **`CELERY_RESULT_BACKEND`**: In Docker, use the service name `redis` (not `localhost`):
  ```
  REDIS_URL=redis://redis:6379/0
  CELERY_BROKER_URL=redis://redis:6379/1
  CELERY_RESULT_BACKEND=redis://redis:6379/2
  ```
  The `.env.example` defaults use `localhost`; override these when running in Docker Compose.
- **Tool-specific env vars**: See `.env.example` for `SYSTEM_LOCATOR_*`, `PRINT_REQUESTS_*`, `RBAC_*`, etc.

### Adding new env vars

1. Add the variable to `.env` with a default or placeholder value.
2. Update `.env.example` with documentation.
3. Restart the web service: `docker compose restart web` or rebuild: `docker compose up -d --build web`.

---

## Data Volumes

The following named volumes persist data across container restarts:

| Volume | Mounted at | Purpose |
|--------|-----------|---------|
| `db-data` | `/data/db` | SQLite databases (inventory, RF chamber, print requests, etc.) |
| `upload-data` | `/data/uploads` | User-uploaded 3D model files and images |
| `generated-data` | `/data/generated` | QR codes and other generated assets |
| `redis-data` | `/var/lib/redis/data` | Redis persistent snapshot (RDB file) |

### Backup data volumes

```bash
# Backup all volumes to a tarball
docker run --rm -v lab-tech-portal_db-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/db-data-backup.tar.gz -C /data .

# Backup just the SQLite directory
docker compose exec web tar czf /backup/db-backup.tar.gz -C /data/db .
```

### Restore data from backup

```bash
# Restore to a named volume
docker run --rm -v lab-tech-portal_db-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/db-data-backup.tar.gz -C /data

# Then restart services
docker compose up -d
```

---

## Backup and Restore

### Full backup (all volumes)

```bash
docker compose stop
docker run --rm \
  -v lab-tech-portal_db-data:/db-data \
  -v lab-tech-portal_upload-data:/upload-data \
  -v lab-tech-portal_generated-data:/generated-data \
  -v lab-tech-portal_redis-data:/redis-data \
  -v $(pwd):/backup \
  alpine tar czf /backup/full-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C / db-data upload-data generated-data redis-data
docker compose up -d
```

### Full restore

```bash
docker compose stop
docker run --rm \
  -v lab-tech-portal_db-data:/db-data \
  -v lab-tech-portal_upload-data:/upload-data \
  -v lab-tech-portal_generated-data:/generated-data \
  -v lab-tech-portal_redis-data:/redis-data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/full-backup-YYYYMMDD-HHMMSS.tar.gz -C /
docker compose up -d
```

---

## Common Tasks

### Run a one-off command in the web container

```bash
docker compose exec web python app.py --help
docker compose exec web flask shell
docker compose exec web pytest
```

### Rebuild the web image after code changes

```bash
docker compose up -d --build web
```

### Inspect the Dockerfile build stages

```bash
docker build --target web --progress=plain .
docker build --target worker --progress=plain .
docker build --target beat --progress=plain .
```

### Monitor resource usage

```bash
docker stats lab-tech-portal-web-1 lab-tech-portal-redis-1
```

---

## Troubleshooting

### Port 8000 already in use

```bash
# Find the process using port 8000
lsof -i :8000

# Either stop the process or change the port in docker-compose.yml
PORT=8001 docker compose up -d
```

### Redis connection refused

```bash
# Check redis service is running
docker compose ps redis

# Restart redis
docker compose restart redis

# Verify from the redis container itself (redis-cli is not installed in the web container)
docker compose exec redis redis-cli ping
```

### Web service fails to start (health check)

```bash
# Check logs
docker compose logs web

# The healthcheck pings /healthz — make sure the Flask app is responding
docker compose exec web curl http://localhost:8000/healthz
```

### Database locked (SQLite)

If you see "database is locked" errors, SQLite is experiencing contention. This is a limitation of SQLite; the migration to PostgreSQL (Slice D-part2) will resolve it.

**Workaround**: Stop all containers, wait 10 seconds, restart:
```bash
docker compose down
sleep 10
docker compose up -d
```

### Celery worker / beat not functional

Celery stubs ship in Slice G-part1 but are activated in Slice C (Sprint 3). The containers start but do nothing. This is expected.

---

## Celery Activation (Slice C+)

When Slice C lands (Sprint 3), the worker and beat services will be activated:

```bash
# Currently: no-op stubs
docker compose logs worker  # Shows stub startup only

# After Slice C: real task processing
docker compose logs worker  # Shows task consumption from Redis
```

No changes needed to `docker-compose.yml` — just redeploy with the new image.

---

## Optional Services

Additional services are available beyond the default stack. Some are always-on; others are profile-gated and must be explicitly requested.

### Prometheus (always on)

Prometheus starts automatically with the default stack — no profile flag needed.

```bash
# Access Prometheus UI
open http://localhost:9090
```

### Grafana (profile: grafana)

```bash
# Start with Grafana included
docker compose --profile grafana up -d

# Access Grafana UI at http://localhost:3000
# Default login: admin / admin
# Import the dashboard from docs/grafana/lab-tech-portal-dashboard.json
```

> **Note:** Set `GF_SECURITY_ADMIN_PASSWORD` in `.env` before starting Grafana. The default `admin` password is insecure.

### MinIO — S3-compatible object storage (profile: storage)

MinIO provides an S3-compatible backend for local development when `OBJECT_STORAGE_BACKEND=s3`.

```bash
# Start with MinIO included
docker compose --profile storage up minio

# Access MinIO console at http://localhost:9001
# Default login: minioadmin / minioadmin
```

Then add to `.env`:
```
OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=lab-portal
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
```

---

## CI/CD Integration

See `.github/workflows/ci.yml` for the automated build and test pipeline. The CI workflow:

1. Builds all Docker targets (web, worker, beat)
2. Runs `docker compose config --quiet` to validate compose syntax
3. Runs the test suite inside the web container
4. Publishes images to a registry (future: Slice G-part2)

---

## See Also

- [architecture.md](../architecture.md) — container topology diagram
- [AGENTS.md](../AGENTS.md) — engineering workflows and conventions
- [CLEANUP_PLAN.md](CLEANUP_PLAN.md) — why Docker lands in Slice G-part1

---

## Cold-Start Audit Notes

**Audited**: 2026-05-15 (automated review, issue #124)
**Fixed in this PR**:
- Removed stale "until PR #58 merges" status banner (PR #58 merged)
- Added explicit `git clone` + `cd` prerequisites — new contributors previously had no repo setup step
- Added working-directory context (`# Run from the repo root`) to all commands that lacked it
- Added `SECRET_KEY` generation command (`secrets.token_urlsafe(64)`) — was described as "random string" with no example
- Corrected "Runs web, worker (stub), beat (stub), and redis" — `worker` and `beat` are profile-gated (`profiles: [worker]`) and do NOT start with plain `docker compose up -d`
- Fixed healthcheck troubleshooting: "pings `/`" corrected to "pings `/healthz`" (matches `docker-compose.yml` and `Dockerfile`)
- Fixed `redis-cli` troubleshooting step: `redis-cli` is not installed in the web container; corrected to `docker compose exec redis redis-cli ping`
- Fixed broken `See Also` link: `../CLEANUP_PLAN.md` → `CLEANUP_PLAN.md` (file lives in `docs/`, not repo root)
- Added Optional Services section documenting Prometheus, Grafana (`--profile grafana`), and MinIO (`--profile storage`) — all three exist in `docker-compose.yml` but were undocumented
- Added Redis URL note: `.env.example` defaults use `redis://localhost:…` which breaks in Docker Compose; the correct Docker host is `redis://redis:…`
- Added `docker-compose.dev.yml` note about targeting `web redis` explicitly to avoid harmless but confusing worker/beat stubs

**Follow-up issues filed**: none (all self-contained)

**Outstanding gaps** (require human validation on a clean machine):
- Verify that `docker compose up -d` completes without errors on a fresh macOS/Linux install with no cached images
- Validate that `.env.example` + `SECRET_KEY` generation + `docker compose up -d` is truly sufficient for a first-time contributor with no prior context about Okta or Jira (those integrations are optional, but it is not obvious to a newcomer which vars are truly optional vs. required)
- Confirm the Redis URL note is surfaced prominently enough — a contributor copy-pasting `.env.example` verbatim will hit a Redis connection error if Celery/sessions are enabled

For the formal cold-start validation (human on a clean machine), see issue #124.
