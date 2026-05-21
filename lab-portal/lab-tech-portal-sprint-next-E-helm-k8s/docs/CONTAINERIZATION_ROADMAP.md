# Lab Tech Portal — Containerization & Production Readiness Roadmap

**Created**: 2026-02-27  
**Author**: Ben Brice (with AI architecture assist)  
**Status**: Planning  
**Repo**: `adc-quality/lab-tech-portal`  
**Project Board**: Lab Tech Portal Tracker (#23)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Assessment](#current-state-assessment)
3. [Architecture Deficiencies](#architecture-deficiencies)
4. [Target Architecture](#target-architecture)
5. [Phase 1 — Production-Ready Foundations](#phase-1--production-ready-foundations)
6. [Phase 2 — Async Task Layer (Celery + Redis)](#phase-2--async-task-layer-celery--redis)
7. [Phase 3 — Docker Containerization](#phase-3--docker-containerization)
8. [Phase 4 — Kubernetes Readiness](#phase-4--kubernetes-readiness)
9. [Cross-Cutting Concerns](#cross-cutting-concerns)
10. [Sprint Planning Guidance](#sprint-planning-guidance)
11. [Risk Register](#risk-register)
12. [Decision Log](#decision-log)

---

## Executive Summary

The Lab Tech Portal is a modular Flask application that manages lab operations across five tools (Inventory, RF Chamber, Checkout, System Locator, 3D Print Requests) with Jira and Okta integrations. It currently runs as a single-process development server with SQLite databases scattered across tool directories and no containerization.

This roadmap defines a phased approach to transform the portal into a production-grade, containerized application suitable for Docker Desktop deployment today and Kubernetes in the future. The work is organized into **4 phases** with approximately **40+ trackable issues** across an estimated **6-8 sprints**.

---

## Current State Assessment

### What Works Well
- **Modular blueprint architecture** — each tool is self-contained with its own templates, static files, and database
- **Okta OIDC authentication** — proper SSO with graceful degradation when not configured
- **Jira integration** — Lab Request ticket creation, attachments, transitions
- **Test suite** — 36 tests passing with safe Jira test exclusion via pytest markers
- **Daily workflow** — `start_day.sh` / `end_day.sh` changelog system

### Current Infrastructure Layout

```
lab-tech-portal/
├── app.py                          ← Flask app factory (single file)
├── services/
│   ├── jira_service.py             ← Jira REST API client (672 lines)
│   └── okta_auth.py                ← Okta OIDC service (210 lines)
├── tools/
│   ├── inventory/
│   │   ├── inventory_app.py        ← Blueprint + inline DB schema
│   │   ├── inventory.db            ← SQLite (created at import time)
│   │   └── static/                 ← QR code PNGs generated at runtime
│   ├── rf_chamber/
│   │   ├── rf_chamber_app.py       ← Blueprint + inline DB schema
│   │   ├── rf_chambers.db          ← SQLite (created at import time)
│   │   └── data/rf_chambers.csv    ← Seed data
│   ├── checkout/
│   │   ├── checkout_app.py         ← Blueprint
│   │   ├── db.py                   ← Schema + migrations
│   │   └── checkout.db             ← SQLite (created at import time)
│   ├── system_locator/
│   │   ├── system_locator_app.py   ← Blueprint (hardcoded PIN "9420")
│   │   ├── db.py                   ← Schema + migrations + Jira import
│   │   └── systems.db              ← SQLite (created at import time)
│   └── print_requests/
│       ├── print_requests_app.py   ← Blueprint + Jira sync
│       ├── db.py                   ← Schema + migrations
│       ├── print_requests.db       ← SQLite (created at import time)
│       └── uploads/                ← User-uploaded files (absolute paths in DB)
├── templates/                      ← Shared base templates
├── static/                         ← Shared CSS
└── tests/                          ← pytest suite (36 tests)
```

### Technology Stack

| Layer | Current | Notes |
|---|---|---|
| **Runtime** | Python 3.9+ | Local venv |
| **Framework** | Flask 3.1.2 | Development server only |
| **WSGI Server** | None (dev server) | `app.run(debug=True)` |
| **Database** | 5× SQLite files | No connection pooling, no ORM |
| **Task Queue** | None | Jira calls are synchronous |
| **Cache** | None | Jira import has in-memory TTL cache |
| **Auth** | Okta OIDC + Flask-Login | Session-based, server cookie |
| **File Storage** | Local filesystem | Absolute paths stored in DB |
| **Logging** | Python stdlib | Unstructured, no request correlation |
| **Containerization** | None | No Dockerfile, no compose |
| **CI/CD** | None | Manual testing and deployment |

---

## Architecture Deficiencies

### Critical (Must Fix Before Docker)

| # | Deficiency | Impact | Affected Components |
|---|---|---|---|
| ~~**D1**~~ | ~~**SQLite files inside source tree**~~ | ✓ shipped in Slice D-part1 — all tools now set `DB_PATH = <DATA_DIR>/db/<tool>.db` at startup and `docker-compose.yml` mounts the `db-data` named volume to `/data/db`. Source tree is no longer the source of truth. | All 5 tools |
| ~~**D2**~~ | ~~**Absolute filesystem paths stored in DB**~~ | ✓ shipped in Slice D-part1 — print-request paths normalized to relative via `.scripts/migrate_print_request_paths.py`; uploads write under `DATA_DIR/uploads/` and store relative keys in DB. | Print Requests |
| ~~**D3**~~ | ~~**No production WSGI server**~~ | ✓ shipped in Sprint 2 (Slice G-part1, PR #58) — Gunicorn serves Flask with 4 workers, TLS-ready | app.py |
| ~~**D4**~~ | ~~**DB initialization at module import time**~~ | ✓ shipped in Sprint 2 (Slice 0b, PR #50) — deferred init via `init_app()` pattern; all tool blueprints register with Flask app factory | All 5 tools |
| ~~**D5**~~ | ~~**No health check endpoint**~~ | ✓ shipped in Sprint 4 (Slice A + observability, PR #51) — `/healthz` (liveness) and `/readyz` (readiness) with Redis health check (PR #89) | app.py |

### High (Should Fix for Robustness)

| # | Deficiency | Impact | Affected Components |
|---|---|---|---|
| ~~**D6**~~ | ~~**Synchronous Jira API calls in request cycle**~~ | ✓ shipped in Sprint 3 (Slice C, PR #97, #70) — async Celery tasks for all Jira operations (create ticket, upload attachment, sync import) with retry + backoff | Print Requests, System Locator |
| ~~**D7**~~ | ~~**Hardcoded secrets and configuration**~~ | ✓ shipped across Sprints 2–4 — PIN, assignee, priorities all moved to env vars in config.py; Jira transition IDs already in .env | System Locator, Print Requests |
| **D8** | **No connection pooling or DB lifecycle management** (planned: Sprint 8) | Each request opens a new `sqlite3.connect()` and there's no use of Flask's `g` or `teardown_appcontext` for cleanup. WAL mode mitigates (PR #77); full connection pooling requires SQLAlchemy + PostgreSQL. | All 5 tools |
| ~~**D9**~~ | ~~**No structured logging**~~ | ✓ shipped in Sprint 4 (Slice B, logging_config.py) — JSON-formatted logs with request ID correlation, user email, tool context | All services |
| ~~**D10**~~ | ~~**No API layer (JSON)**~~ | ✓ shipped in Sprint 5 (Slice H, PR #73, #91) — `/api/v1/` blueprint with JSON endpoints for all 5 tools, Swagger/OpenAPI docs at `/api/v1/docs` | All 5 tools |

### Medium (Improve for Production Quality)

| # | Deficiency | Impact | Affected Components |
|---|---|---|---|
| **D11** | **No graceful shutdown handling** (planned: Sprint 8) | SIGTERM from Docker stop doesn't flush DB connections or complete in-flight Jira calls. Gunicorn handles HTTP gracefully; Celery workers need improved signal handling. | app.py, celery_app.py |
| ~~**D12**~~ | ~~**No rate limiting**~~ | ✓ shipped in Sprint 5+ (Flask-Limiter integrated) — rate limits enforced on public endpoints (10 req/min per IP default) | All routes |
| **D13** | **No CORS configuration** (partial) | Basic CORS policy in place (`Flask-CORS` initialized in `app.py`). Per-origin allow-list refinement still open if a cross-origin SPA is added. Not blocking on the Sprint 8 plan. | app.py |
| **D14** | **Session storage is server-side cookies only** (planned: Sprint 8) | Flask's default cookie-based sessions don't scale across multiple replicas. Session data lost on restart. Sprint 8 D-part5 moves to Redis-backed sessions. | Auth |
| **D15** | **No database migration framework** (planned: Sprint 8) | Ad-hoc `_migrate_schema()` functions with `ALTER TABLE` and `PRAGMA table_info` checks. Fragile and not auditable. Sprint 8 D-part4 introduces Alembic. | Checkout, System Locator, Print Requests |
| ~~**D16**~~ | ~~**No CI/CD pipeline**~~ | ✓ shipped in Sprint 2 (Slice G-part1, PR #58) — GitHub Actions workflow runs tests, builds Docker image, pushes to registry on every merge | Infrastructure |
| **D17** | **Inline DB schemas in route files** (planned: Sprint 8) | Inventory and RF Chamber define schemas inside their blueprint files instead of separate DB modules. Full SQLAlchemy migration in Sprint 8 will extract these. | Inventory, RF Chamber |
| **D18** | **No backup strategy for SQLite files** (planned: Sprint 8) | Database files have SQLite WAL mode enabled (PR #77, Sprint 4); pg_dump scheduled job planned for Sprint 8 after PostgreSQL migration. | All 5 tools |
| **D19** | **Static CSS build requires manual step** | `tools/build_static.py` concatenates CSS files manually. No watch mode, no integration with app startup. Low priority; can defer to post-Sprint-8 QoL improvements. | Static assets |
| ~~**D20**~~ | ~~**No environment-specific configuration**~~ | ✓ shipped in Sprint 2 (Slice A, config.py) — BaseConfig, DevelopmentConfig, ProductionConfig, TestingConfig classes; validates secrets at startup | app.py |

---

## Target Architecture

### Docker Compose Topology (Phase 3 End State)

```
┌─────────────────────────────────────────────────────────────────┐
│                       docker-compose.yml                         │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │   web    │  │  worker  │  │   beat   │  │    redis      │   │
│  │ Gunicorn │  │  Celery  │  │  Celery  │  │  Message      │   │
│  │  Flask   │  │  Worker  │  │   Beat   │  │  Broker       │   │
│  │ :8000    │  │          │  │          │  │  :6379        │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘   │
│       │              │              │                │           │
│       └──────────────┴──────────────┴────────────────┘           │
│                              │                                   │
│  ┌───────────────────────────┴──────────────────────────────┐   │
│  │                    Shared Volumes                         │   │
│  │  /data/db/          → All 5 SQLite databases             │   │
│  │  /data/uploads/     → Print request files & images       │   │
│  │  /data/static/gen/  → Generated QR codes                 │   │
│  │  /data/backups/     → Scheduled DB backup snapshots      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Kubernetes End State (Phase 4)

```
┌──────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                         │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Deployment: web (2+ replicas)                              │ │
│  │  ┌──────────┐  ┌──────────┐                                 │ │
│  │  │ Pod: web  │  │ Pod: web  │  ← HPA scales on CPU/memory  │ │
│  │  │ Gunicorn  │  │ Gunicorn  │                                │ │
│  │  └──────────┘  └──────────┘                                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                  │
│  │ Deployment: worker │  │ Deployment: beat   │                  │
│  │ Celery (2 replicas)│  │ Celery Beat (1)    │                  │
│  └────────────────────┘  └────────────────────┘                  │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                  │
│  │ Service: PostgreSQL│  │ Service: Redis     │                  │
│  │ (PersistentVolume) │  │ (PersistentVolume) │                  │
│  └────────────────────┘  └────────────────────┘                  │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                  │
│  │ Ingress            │  │ ConfigMap/Secrets  │                  │
│  │ (nginx/traefik)    │  │ (.env equivalent)  │                  │
│  └────────────────────┘  └────────────────────┘                  │
│                                                                   │
│  ┌────────────────────┐                                          │
│  │ S3/MinIO           │  ← File uploads (replaces local FS)     │
│  │ (Object Storage)   │                                          │
│  └────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Production-Ready Foundations

**Goal**: Make the existing app containerizable without changing its behavior.  
**Estimated Effort**: 2-3 sprints  
**Dependencies**: None — can start immediately

### 1.1 Centralize Data Directory Configuration

**What**: Replace all hardcoded `os.path.dirname(__file__)` database paths with a single `DATA_DIR` environment variable. Each tool derives its database path from `DATA_DIR`.

**Current State**:
```python
# tools/inventory/inventory_app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "inventory.db")

# tools/rf_chamber/rf_chamber_app.py
DB_FILE = os.path.join(BASE_DIR, "rf_chambers.db")

# tools/checkout/db.py
DB_PATH = os.path.join(BASE_DIR, "checkout.db")

# tools/system_locator/db.py
DB_PATH = os.path.join(BASE_DIR, "systems.db")

# tools/print_requests/db.py
DB_PATH = os.path.join(BASE_DIR, "print_requests.db")
```

**Target State**:
```python
# config.py (new file)
import os
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_DIR = os.path.join(DATA_DIR, "db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
GENERATED_DIR = os.path.join(DATA_DIR, "generated")
```

**Files to Change**: `inventory_app.py`, `rf_chamber_app.py`, `checkout/db.py`, `system_locator/db.py`, `print_requests/db.py`, `conftest.py`

### 1.2 Fix Absolute Path Storage in Print Requests

**What**: Store relative paths (relative to `UPLOAD_DIR`) in the database instead of absolute filesystem paths. Update file-serving routes to reconstruct full paths from `UPLOAD_DIR` + relative path.

**Current**: `uploaded_file_path = "/home/user/lab-tech-portal/tools/print_requests/uploads/abc.stl"`  
**Target**: `uploaded_file_path = "abc.stl"` (resolved at runtime via `os.path.join(UPLOAD_DIR, row["uploaded_file_path"])`)

### 1.3 Defer Database Initialization

**What**: Move all `init_db()` / `_ensure_db()` calls from module-level import time into Flask's `app.before_first_request` or an explicit `init_app(app)` pattern. This prevents database creation as a side effect of importing.

**Current**:
```python
# Bottom of rf_chamber_app.py
_ensure_db()  # runs when Python imports this module
```

**Target**:
```python
def init_app(app):
    with app.app_context():
        _ensure_db()

# In app.py
from tools.rf_chamber.rf_chamber_app import rf_chamber_bp, init_app as rf_init
rf_init(app)
```

### 1.4 Add Production WSGI Server

**What**: Add `gunicorn` (Linux) to requirements. Create entrypoint scripts for production vs. development.

**New Files**:
- `requirements-prod.txt` — production-only dependencies (gunicorn, etc.)
- `entrypoint.sh` — production startup script
- `wsgi.py` — WSGI entry point (`from app import app`)

### 1.5 Extract Hardcoded Values to Environment Variables

**What**: Move all hardcoded configuration to `.env` / environment variables.

| Current Hardcoded Value | New Environment Variable | File |
|---|---|---|
| `"9420"` (delete PIN) | `SYSTEM_LOCATOR_DELETE_PIN` | `system_locator_app.py` |
| `"bbrice"` (default assignee) | `PRINT_REQUESTS_DEFAULT_ASSIGNEE` | `print_requests_app.py` |
| `"P4: Low"` (default priority) | `PRINT_REQUESTS_DEFAULT_PRIORITY` | `print_requests_app.py` |
| `"Other"` (request type) | `PRINT_REQUESTS_DEFAULT_REQUEST_TYPE` | `print_requests_app.py` |
| Jira transition IDs | Already env vars | ✅ |

### 1.6 Add Health Check Endpoint

**What**: Create `/healthz` (liveness) and `/readyz` (readiness) endpoints that verify database connectivity.

```python
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

@app.route("/readyz")
def readyz():
    errors = []
    for name, path in db_paths.items():
        if not os.path.exists(path):
            errors.append(f"{name}: database file missing")
    if errors:
        return {"status": "not ready", "errors": errors}, 503
    return {"status": "ready"}, 200
```

### 1.7 Centralize Configuration Management

**What**: Create a configuration module with environment-specific classes (Dev, Test, Production) instead of ad-hoc `os.environ.get()` calls throughout the codebase.

```python
# config.py
class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-fallback")
    DATA_DIR = os.environ.get("DATA_DIR", "./data")
    ...

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    LOGIN_DISABLED = True

class ProductionConfig(BaseConfig):
    DEBUG = False
    LOGIN_DISABLED = False
```

### 1.8 Add Config Validation on Startup

**What**: Fail fast if required environment variables are missing. Log all configuration (with secrets redacted) at startup.

### 1.9 Restructure DB Modules

**What**: Extract inline SQL schemas from `inventory_app.py` and `rf_chamber_app.py` into dedicated `db.py` files, consistent with the pattern used by checkout, system locator, and print requests.

### 1.10 Add `.env.example`

**What**: Create a documented `.env.example` file listing every environment variable the app uses, with descriptions and example values.

---

## Phase 2 — Async Task Layer (Celery + Redis)

**Goal**: Move long-running operations (Jira API calls) out of the HTTP request/response cycle.  
**Estimated Effort**: 2 sprints  
**Dependencies**: Phase 1 (centralized config, deferred init)

### 2.1 Add Redis as Message Broker

**What**: Add Redis to the stack as Celery's message broker and result backend. In development, Redis runs locally or via Docker; in production, it's a Docker Compose service.

**New Dependencies**: `celery`, `redis`

### 2.2 Create Celery Application

**What**: Create `celery_app.py` alongside `app.py` with shared Flask config.

```python
# celery_app.py
from celery import Celery

def make_celery(app):
    celery = Celery(app.import_name, broker=app.config["CELERY_BROKER_URL"])
    celery.conf.update(app.config)
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask
    return celery
```

### 2.3 Migrate Jira Operations to Celery Tasks

**What**: Wrap all Jira API calls in Celery tasks with retry logic.

| Task | Trigger | Retry Policy |
|---|---|---|
| `tasks.create_jira_ticket` | Print request submission | 3 retries, exponential backoff |
| `tasks.transition_jira_ticket` | Status change (cancel/close) | 3 retries, 30s delay |
| `tasks.upload_jira_attachment` | File upload during submission | 3 retries, exponential backoff |
| `tasks.sync_jira_import` | System locator import button | 2 retries, 60s delay |

### 2.4 Add Task Status Tracking

**What**: Add `task_status` and `task_id` columns to relevant database tables. Update UI to show pending/success/error states for async operations.

**New DB Fields**:
- `print_requests.jira_task_status` — `pending | processing | synced | error`
- `print_requests.jira_task_id` — Celery task UUID for status polling

### 2.5 Add Celery Beat Scheduled Tasks

**What**: Configure periodic tasks via Celery Beat.

| Scheduled Task | Frequency | Description |
|---|---|---|
| `periodic.sync_jira_systems` | Every 15 minutes | Auto-import new Jira lab requests into System Locator |
| `periodic.check_stale_checkouts` | Daily at 9:00 AM | Flag equipment past `return_date` |
| `periodic.backup_databases` | Daily at 2:00 AM | Copy SQLite files to backup volume |
| `periodic.cleanup_temp_uploads` | Weekly | Remove orphaned upload files |

### 2.6 Add Task Status API Endpoints

**What**: Create polling endpoints for the UI to check async task progress.

```
GET /api/v1/tasks/<task_id>/status → {"state": "SUCCESS", "result": {"jira_key": "QENG-1234"}}
```

### 2.7 Update UI for Async Feedback

**What**: Modify print request submission and system locator import UI to show "Processing..." state with auto-refresh or polling for completion.

---

## Phase 3 — Docker Containerization

**Goal**: Package the full application (web + worker + beat + redis) into a Docker Compose stack.  
**Estimated Effort**: 1-2 sprints  
**Dependencies**: Phase 1 (paths centralized), Phase 2 (Celery configured)

### 3.1 Create Dockerfile

**What**: Multi-stage Dockerfile with separate targets for web, worker, and beat.

```dockerfile
# ---- Base ----
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt
COPY . .
ENV DATA_DIR=/data
RUN mkdir -p /data/db /data/uploads /data/generated /data/backups

# ---- Web ----
FROM base AS web
EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "120", "wsgi:app"]

# ---- Worker ----
FROM base AS worker
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]

# ---- Beat ----
FROM base AS beat
CMD ["celery", "-A", "celery_app", "beat", "--loglevel=info"]
```

### 3.2 Create docker-compose.yml

**What**: Define the full stack with proper volume mounts, networking, and environment.

```yaml
services:
  web:
    build: { context: ., target: web }
    ports: ["8000:8000"]
    env_file: .env
    volumes:
      - db-data:/data/db
      - upload-data:/data/uploads
      - generated-data:/data/generated
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  worker:
    build: { context: ., target: worker }
    env_file: .env
    volumes:
      - db-data:/data/db
      - upload-data:/data/uploads
    depends_on:
      redis:
        condition: service_healthy

  beat:
    build: { context: ., target: beat }
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    volumes:
      - redis-data:/data

volumes:
  db-data:
  upload-data:
  generated-data:
  redis-data:
```

### 3.3 Create .dockerignore

**What**: Exclude development artifacts from the Docker build context.

### 3.4 Create wsgi.py Entry Point

**What**: Clean WSGI entry point that imports and configures the app.

### 3.5 Create entrypoint.sh

**What**: Shell script that runs database initialization before starting the server. Handles first-run setup.

```bash
#!/bin/bash
set -e
echo "Initializing databases..."
python -c "from app import app; app.app_context().__enter__()"
echo "Starting Gunicorn..."
exec gunicorn -w ${GUNICORN_WORKERS:-4} -b 0.0.0.0:${PORT:-8000} wsgi:app
```

### 3.6 Add Docker Development Workflow

**What**: `docker-compose.dev.yml` overlay for local development with hot reload, debug mode, and source mounting.

### 3.7 SQLite WAL Mode and Concurrency

**What**: Enable SQLite WAL (Write-Ahead Logging) mode for better concurrent read/write performance across web and worker containers sharing the same database files.

```python
def _get_connection():
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

### 3.8 Add Docker Build to CI/CD

**What**: GitHub Actions workflow to build and test the Docker image on every push.

---

## Phase 4 — Kubernetes Readiness

**Goal**: Prepare the application for multi-replica Kubernetes deployment.  
**Estimated Effort**: 3-4 sprints (longer timeline, can be parallel with improvements)  
**Dependencies**: Phase 3 (Docker working)

### 4.1 Migrate from SQLite to PostgreSQL

**What**: Replace all 5 SQLite databases with a single PostgreSQL instance. This is required because SQLite does not support concurrent writes from multiple pods.

**Approach**:
- Introduce SQLAlchemy as the ORM layer
- Create models for all 5 tools
- Write a data migration script to move existing SQLite data to PostgreSQL
- Update all `db.py` modules to use SQLAlchemy sessions

### 4.2 Add Alembic for Schema Migrations

**What**: Replace ad-hoc `_migrate_schema()` functions with Alembic, providing versioned, auditable, reversible schema migrations.

### 4.3 Replace Local File Storage with Object Storage

**What**: Move uploaded files (print request STL/3MF, design images, generated QR codes) to S3-compatible object storage (MinIO for on-prem, S3 for cloud).

### 4.4 Externalize Session Storage to Redis

**What**: Move Flask sessions from server-side cookies to Redis using `flask-session`. This allows sessions to persist across pod restarts and be shared across replicas.

### 4.5 Create Kubernetes Manifests

**What**: Helm chart or Kustomize manifests for deploying the full stack.

- Deployments: web (2+ replicas), worker (2 replicas), beat (1 replica)
- Services: web (ClusterIP), PostgreSQL, Redis
- Ingress: nginx/traefik with TLS
- ConfigMaps: non-secret configuration
- Secrets: database credentials, Jira PAT, Okta secrets
- PersistentVolumeClaims: PostgreSQL data, Redis data, file uploads
- HorizontalPodAutoscaler: web + worker

### 4.6 Add Prometheus Metrics

**What**: Instrument the Flask app with `prometheus-flask-instrumentator` for standard HTTP metrics, plus custom metrics for Jira task success/failure rates, queue depth, etc.

### 4.7 Database Connection Pooling

**What**: Configure SQLAlchemy connection pooling (pool_size, max_overflow, pool_recycle) for production PostgreSQL usage.

### 4.8 Add Database Backup CronJob

**What**: Kubernetes CronJob that runs `pg_dump` on a schedule and stores backups in object storage.

---

## Cross-Cutting Concerns

These items span multiple phases and should be addressed incrementally throughout.

### CC1. Structured Logging

**What**: Replace ad-hoc `logging.getLogger()` usage with a centralized logging configuration.

- JSON-formatted log output (machine-parseable for log aggregation)
- Request ID middleware — attach a UUID to every HTTP request, propagate through all log messages
- Correlation with Celery task IDs
- Log level configurable via environment variable (`LOG_LEVEL=INFO`)

### CC2. Error Handling and Resilience

**What**: Comprehensive error handling strategy.

- Global `@app.errorhandler(500)` with structured error response
- Blueprint-level error handlers for tool-specific errors
- Jira API retry logic with `urllib3.Retry` / `requests.adapters.HTTPAdapter`
- Circuit breaker pattern for external service calls (optional, advanced)

### CC3. API Layer (JSON Endpoints)

**What**: Add a `/api/v1/` blueprint that exposes JSON endpoints parallel to every HTML route. This enables:

- Future SPA frontend (React, Vue, HTMX)
- External script integration
- Mobile app readiness
- Celery task status polling

| HTML Route | API Equivalent |
|---|---|
| `GET /inventory/` | `GET /api/v1/inventory/items` |
| `POST /inventory/add` | `POST /api/v1/inventory/items` |
| `GET /print-requests/` | `GET /api/v1/print-requests` |
| `POST /print-requests/submit` | `POST /api/v1/print-requests` |
| `GET /systems/` | `GET /api/v1/systems` |
| `GET /rf-chamber/` | `GET /api/v1/rf-chambers` |
| `GET /checkout/` | `GET /api/v1/checkout/equipment` |

### CC4. Security Hardening

- Move PIN to environment variable
- Add CSRF protection (Flask-WTF)
- Add rate limiting (Flask-Limiter)
- Content Security Policy headers
- Secure cookie flags in production
- Input validation middleware

### CC5. Testing Infrastructure

- Docker-based integration test suite (`docker-compose.test.yml`)
- Test fixtures for Celery tasks (using `celery.contrib.testing`)
- Coverage reporting with threshold enforcement
- GitHub Actions CI pipeline running tests on every PR

### CC6. Documentation

- Update `architecture.md` with new Docker/Celery diagrams
- API documentation (OpenAPI/Swagger via Flask-RESTX or apispec)
- Runbook for Docker Compose operations (start, stop, logs, backup, restore)
- Troubleshooting guide for common container issues

---

## Sprint Planning Guidance

### Suggested Sprint Breakdown

| Sprint | Phase | Focus | Key Deliverables |
|---|---|---|---|
| **Sprint 1** | Phase 1 | Config & Paths | Centralized config, DATA_DIR, fix absolute paths, `.env.example` |
| **Sprint 2** | Phase 1 | Server & Init | Gunicorn, deferred init, health checks, DB module restructure |
| **Sprint 3** | Phase 1 + CC | Hardening | Extract hardcoded values, structured logging, error handling |
| **Sprint 4** | Phase 2 | Celery Core | Redis, Celery app, migrate Jira tasks, task status tracking |
| **Sprint 5** | Phase 2 + 3 | Beat + Docker | Celery Beat scheduled tasks, Dockerfile, docker-compose.yml |
| **Sprint 6** | Phase 3 | Docker Polish | Dev overlay, CI/CD, WAL mode, integration tests |
| **Sprint 7** | CC | API + Security | JSON API layer, CSRF, rate limiting, CORS |
| **Sprint 8** | Phase 4 | K8s Prep | SQLAlchemy/Alembic, PostgreSQL migration |

### Definition of Done per Issue

- [ ] Code implemented and passing linter
- [ ] Unit tests added/updated
- [ ] Existing tests still pass (`python -m pytest`)
- [ ] Manual testing performed
- [ ] Documentation updated (if applicable)
- [ ] Changelog entry created
- [ ] PR reviewed and merged

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| SQLite concurrent write issues with Docker volumes | High | Medium | Enable WAL mode (Phase 3.7); plan PostgreSQL migration (Phase 4) |
| Celery adds complexity for small team | Medium | Medium | Start with simple tasks; Celery is replaceable with `rq` if needed |
| Test suite breaks during refactoring | Medium | High | Run tests after every change; keep `conftest.py` updated |
| Jira API rate limiting under Celery | Low | Medium | Add rate limiting to Celery tasks; respect Jira's `429` responses |
| Docker Desktop licensing restrictions | Low | Low | Evaluate Podman or Rancher Desktop as alternatives |
| Breaking changes to existing URLs | Low | High | Keep HTML routes unchanged; add API as additive layer |

---

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|---|---|---|---|
| 2026-02-27 | Use Celery + Redis for async tasks | Industry standard, well-documented, supports scheduled tasks | `rq` (simpler but less feature-rich), `dramatiq` (newer, smaller community) |
| 2026-02-27 | Keep SQLite for Docker phase, migrate to PostgreSQL for K8s | SQLite works fine for single-writer Docker; PostgreSQL needed for multi-replica | Start with PostgreSQL immediately (rejected: too large a change in one step) |
| 2026-02-27 | Multi-stage Dockerfile with shared base | Single image source, minimal duplication, separate concerns | Separate Dockerfiles per service (rejected: maintenance overhead) |
| 2026-02-27 | Add API layer alongside templates (not replace) | Zero disruption to current users; gradual migration path | Full SPA rewrite (rejected: too much work, breaks existing workflow) |
| 2026-02-27 | Gunicorn as WSGI server | Standard for Python/Flask, well-supported in Docker | uWSGI (heavier), Waitress (Windows-native, less Docker-standard) |

---

## Appendix: Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes (prod) | `"dev"` | Flask session encryption key |
| `DATA_DIR` | No | `./data` | Root directory for all persistent data |
| `FLASK_ENV` | No | `development` | `development` or `production` |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `GUNICORN_WORKERS` | No | `4` | Number of Gunicorn worker processes |
| `PORT` | No | `8000` | HTTP port |
| `REDIS_URL` | Phase 2+ | — | Redis connection URL |
| `CELERY_BROKER_URL` | Phase 2+ | — | Celery broker URL (usually same as REDIS_URL) |
| `OKTA_ISSUER` | No | — | Okta OIDC issuer URL (disables auth if unset) |
| `OKTA_CLIENT_ID` | No | — | Okta OIDC client ID |
| `OKTA_CLIENT_SECRET` | No | — | Okta OIDC client secret |
| `OKTA_REDIRECT_URI` | No | — | Okta OIDC redirect URI |
| `JIRA_URL` | No | — | Jira server base URL |
| `JIRA_PAT` | No | — | Jira Personal Access Token |
| `PRINT_REQUESTS_CREATE_JIRA` | No | `false` | Enable Jira ticket creation for print requests |
| `PRINT_REQUESTS_DEFAULT_ASSIGNEE` | No | `bbrice` | Default Jira assignee for print requests |
| `PRINT_REQUESTS_DEFAULT_PRIORITY` | No | `P4: Low` | Default Jira priority |
| `PRINT_REQUESTS_DEFAULT_REQUEST_TYPE` | No | `Other` | Default Jira lab request type |
| `PRINT_REQUESTS_JIRA_CANCEL_TRANSITION_ID` | No | — | Jira transition ID for cancel |
| `PRINT_REQUESTS_JIRA_CLOSE_TRANSITION_ID` | No | — | Jira transition ID for close |
| `SYSTEM_LOCATOR_DELETE_PIN` | No | `9420` | PIN for hard-delete authorization |
| `SYSTEM_LOCATOR_JIRA_CACHE_TTL` | No | `300` | Jira import cache TTL in seconds |
| `RF_CHAMBER_BASE_URL` | No | — | Base URL for QR code generation |
