#!/bin/sh
# entrypoint.sh — container startup script (Slice G-part1, issue #22)
#
# Runs database initialisation then hands off to Gunicorn. All settings are
# driven by environment variables so the image is environment-agnostic.
#
# Environment variables (all have defaults, see .env.example):
#   DATA_DIR           — root for SQLite files and uploads  (default: /data)
#   PORT               — TCP port Gunicorn listens on       (default: 8000)
#   GUNICORN_WORKERS   — number of Gunicorn worker processes (default: 4)
#   GUNICORN_TIMEOUT   — worker timeout in seconds          (default: 120)
set -e

# ---------------------------------------------------------------------------
# Ensure data sub-directories exist (may not be present on a fresh volume).
# ---------------------------------------------------------------------------
DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "${DATA_DIR}/db" "${DATA_DIR}/uploads" "${DATA_DIR}/generated" "${DATA_DIR}/backups"

# ---------------------------------------------------------------------------
# Database initialisation — Flask app-context call (safe at startup only).
# ---------------------------------------------------------------------------
echo "[entrypoint] Initialising databases…"
python - <<'PYEOF'
import app as _app_module
with _app_module.app.app_context():
    # app.py imports each tool module, and those modules call init_app(app)
    # at import time — several implementations (tools/checkout/db.py,
    # tools/print_requests/db.py, tools/system_locator/db.py, etc.) create
    # their SQLite tables eagerly inside init_app via init_db(). By the time
    # we reach this block the DBs are already initialised; we just exercise
    # the app_context so any import-time failure surfaces before Gunicorn
    # spawns workers.
    pass
PYEOF
echo "[entrypoint] Database initialisation complete."

# ---------------------------------------------------------------------------
# Start Gunicorn.
# ---------------------------------------------------------------------------
PORT="${PORT:-8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "[entrypoint] Starting Gunicorn on 0.0.0.0:${PORT} (workers=${GUNICORN_WORKERS}, timeout=${GUNICORN_TIMEOUT}s)…"
exec gunicorn \
    -w "${GUNICORN_WORKERS}" \
    -b "0.0.0.0:${PORT}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    wsgi:app
