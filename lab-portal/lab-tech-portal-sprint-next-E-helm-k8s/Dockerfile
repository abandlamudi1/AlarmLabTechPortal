# Dockerfile — multi-stage build for lab-tech-portal (Slice G-part1, issue #19)
#
# Stages:
#   builder — installs all Python dependencies into /install (never shipped)
#   base    — lean runtime: copies deps from builder, adds app code
#   web     — production WSGI server (Gunicorn)
#   worker  — Celery worker stub (topology only; Slice C activates the app)
#   beat    — Celery beat stub   (topology only; Slice C activates the app)
#   test    — CI test runner: base + pytest (never shipped to production)
#
# Build targets:
#   docker build --target web    -t lab-tech-portal:web .
#   docker build --target worker -t lab-tech-portal:worker .
#   docker build --target beat   -t lab-tech-portal:beat .
#   docker build --target test   -t lab-tech-portal:test .
#
# Data volumes:
#   /data/db          — SQLite databases (migrating to Postgres in Slice D-part2)
#   /data/uploads     — user-uploaded files (3D-print STLs, etc.)
#   /data/generated   — QR codes and other generated assets
#   /data/backups     — backup snapshots

# ---------------------------------------------------------------------------
# Stage: builder — pip install only; image is never shipped
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    -r requirements-prod.txt
# pytest is NOT in requirements.txt — it is installed directly in the test stage
# so the production web image does not carry test dependencies.

# ---------------------------------------------------------------------------
# Stage: base — minimal runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="Lab Tech Portal"
LABEL org.opencontainers.image.source="https://github.com/adc-quality/lab-tech-portal"

# curl is required for the HEALTHCHECK. Only runtime system dep.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from the builder stage.
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source.
COPY . .

# Make the entrypoint executable.
RUN chmod +x entrypoint.sh

# Create DATA_DIR sub-directories so the image is usable even without volumes.
ENV DATA_DIR=/data
RUN mkdir -p /data/db /data/uploads /data/generated /data/backups

# Non-root user for security hardening.
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app /data
USER appuser

# Default runtime environment values — override via env vars or compose.
ENV FLASK_ENV=production \
    PORT=8000 \
    GUNICORN_WORKERS=4 \
    GUNICORN_TIMEOUT=120

EXPOSE 8000

# ---------------------------------------------------------------------------
# Stage: web (production WSGI server)
# ---------------------------------------------------------------------------
FROM base AS web

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/healthz || exit 1

CMD ["./entrypoint.sh"]

# ---------------------------------------------------------------------------
# Stage: worker (Celery worker — topology only, non-functional until Slice C)
# ---------------------------------------------------------------------------
FROM base AS worker

# Sprint 6 Issue #90: env-driven concurrency and queue selection.
# --without-gossip --without-mingle --without-heartbeat reduce Redis broker
# chatter for single-node deployments.  These flags are WORKER-ONLY and must
# NOT be added to the beat CMD.
#
# No ENV default for CELERY_WORKER_CONCURRENCY: the Python config default
# (os.cpu_count() or 2) is the authoritative default.  Operators who want a
# fixed concurrency in containerised deployments should set the env var
# explicitly in docker-compose.yml or their orchestrator.  The :-2 shell
# fallback below is a last-resort safety net only.
ENV CELERY_QUEUES=celery

CMD ["sh", "-c", "exec celery -A app worker --loglevel=info --concurrency=${CELERY_WORKER_CONCURRENCY:-2} -Q ${CELERY_QUEUES:-celery} --without-gossip --without-mingle --without-heartbeat"]

# ---------------------------------------------------------------------------
# Stage: beat (Celery beat — Slice C)
# ---------------------------------------------------------------------------
FROM base AS beat

CMD ["celery", "-A", "app", "beat", "--loglevel=info"]

# ---------------------------------------------------------------------------
# Stage: test — CI test runner (never shipped to production)
# ---------------------------------------------------------------------------
FROM base AS test

# Switch to root to install pytest system-wide — appuser has no home dir for
# --user installs and /usr/local is owned by root.
USER root
RUN pip install --no-cache-dir pytest==9.0.2 pytest-cov==5.0.0 fakeredis==2.30.3 'moto[s3]==5.0.20'
USER appuser

CMD ["python", "-m", "pytest", "tests/", "-x", "-q"]
