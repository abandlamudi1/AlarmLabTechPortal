"""Shared audit log service for security-sensitive operations.

Records every security-sensitive write operation across all 5 tools
to a dedicated SQLite database.

# Pattern: docs/patterns/observability/audit-logging.md
# (qe-architecture-ai-assisted-guide @ 567edc9)

Slice B, Issue #46 — audit log table + /api/v1/audit-log endpoint.

Usage::

    from services.audit_log import log_event

    log_event(
        actor="user@example.com",
        action="checkout.checkout",
        resource_type="equipment",
        resource_id=42,
        detail={"item_name": "Oscilloscope"},
    )

Configuration:
  - DB path defaults to DATA_DIR/db/audit.db
  - Override via AUDIT_LOG_DB_PATH environment variable
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.logging_config import get_logger

logger = get_logger(__name__)

# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH: str = os.environ.get("AUDIT_LOG_DB_PATH", "./data/db/audit.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    detail TEXT,
    timestamp TEXT NOT NULL
)
"""


def _get_connection() -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection to the audit DB."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    """Create the audit_events table if it does not already exist."""
    with _get_connection() as conn:
        conn.execute(_SCHEMA)


def log_event(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: Any,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a security-sensitive event to the audit log.

    Args:
        actor: The authenticated user's email address.
        action: A dot-namespaced string such as ``"checkout.return"``
            or ``"system_locator.hard_delete"``.
        resource_type: The type of resource being acted on (e.g.
            ``"equipment"``, ``"system"``, ``"endpoint"``).
        resource_id: The identifier for the resource. Converted to str
            for storage.
        detail: Optional dict of additional structured context.  Must
            be JSON-serialisable.
    """
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    detail_json = json.dumps(detail) if detail is not None else None
    try:
        with _get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events
                    (actor, action, resource_type, resource_id, detail, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (actor, action, str(resource_type), str(resource_id), detail_json, timestamp),
            )
    except Exception as exc:  # noqa: BLE001 — never let audit failure crash the request
        logger.warning(
            "audit_log_write_failure",
            actor=actor,
            action=action,
            error=str(exc),
        )


def get_recent_events(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Return recent audit events, newest first.

    Args:
        limit: Maximum number of rows to return (default 50).
        offset: Row offset for pagination (default 0).

    Returns:
        A list of dicts, each with keys: id, actor, action,
        resource_type, resource_id, detail, timestamp.
    """
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, actor, action, resource_type, resource_id, detail, timestamp
            FROM audit_events
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    result = []
    for row in rows:
        event = dict(row)
        raw_detail = event.get("detail")
        if raw_detail:
            try:
                event["detail"] = json.loads(raw_detail)
            except (json.JSONDecodeError, TypeError):
                pass  # leave as raw string if unparseable
        result.append(event)
    return result


def init_app(app) -> None:
    """Wire AUDIT_LOG_DB_PATH from app config then initialise the schema.

    Called by app.py immediately after other tool init_app() calls.
    """
    global DB_PATH
    env_override = os.environ.get("AUDIT_LOG_DB_PATH")
    if env_override:
        DB_PATH = env_override
    else:
        data_dir = app.config.get("DATA_DIR", "./data")
        DB_PATH = str(Path(data_dir) / "db" / "audit.db")
    init_db()
