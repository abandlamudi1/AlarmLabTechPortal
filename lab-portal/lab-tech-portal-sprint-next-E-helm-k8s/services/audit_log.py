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
from datetime import datetime, timedelta
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

# Key-value store for admin-configurable settings (e.g. retention policy).
_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

_RETENTION_KEY = "retention_days"


def _get_connection() -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection to the audit DB."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    """Create the audit_events and audit_settings tables if absent."""
    with _get_connection() as conn:
        conn.execute(_SCHEMA)
        conn.execute(_SETTINGS_SCHEMA)


def _utc_cutoff(days: int) -> str:
    """Return the ISO-8601 (seconds) timestamp ``days`` days before now (UTC).

    Matches the format written by ``log_event`` so it can be compared
    lexicographically against the stored ``timestamp`` column.
    """
    return (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")


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


def count_active_users(days: int = 30) -> int:
    """Return the number of distinct actors with events in the last ``days``.

    Args:
        days: Size of the lookback window in days (default 30).

    Returns:
        Count of distinct ``actor`` values whose most recent event falls
        within the window. Returns 0 when there is no activity.
    """
    cutoff = _utc_cutoff(days)
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT actor) AS n FROM audit_events WHERE timestamp >= ?",
            (cutoff,),
        ).fetchone()
    return int(row["n"]) if row and row["n"] is not None else 0


def get_activity_summary(days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
    """Return per-action event counts in the last ``days``, busiest first.

    Each action string is dot-namespaced (e.g. ``"checkout.checkout"``),
    so this is effectively a "most active areas" breakdown.

    Args:
        days: Lookback window in days (default 30).
        limit: Maximum number of action rows to return (default 50).

    Returns:
        A list of dicts with keys ``action`` and ``count``, ordered by
        descending count then action name.
    """
    cutoff = _utc_cutoff(days)
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT action, COUNT(*) AS count
            FROM audit_events
            WHERE timestamp >= ?
            GROUP BY action
            ORDER BY count DESC, action ASC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    return [{"action": row["action"], "count": int(row["count"])} for row in rows]


def get_oldest_event_age_days() -> Optional[int]:
    """Return the age in days of the oldest audit event, or None if no events."""
    with _get_connection() as conn:
        row = conn.execute("SELECT MIN(timestamp) AS oldest FROM audit_events").fetchone()
    if not row or not row["oldest"]:
        return None
    from datetime import datetime, timezone
    try:
        oldest = datetime.fromisoformat(row["oldest"].replace("Z", "+00:00"))
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - oldest
        return max(0, delta.days)
    except (ValueError, AttributeError):
        return None


def get_retention_days() -> Optional[int]:
    """Return the configured retention window in days, or None if disabled.

    A return value of ``None`` (no row, or a stored value of 0/blank) means
    events are kept indefinitely.
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM audit_settings WHERE key = ?",
            (_RETENTION_KEY,),
        ).fetchone()
    if not row or row["value"] in (None, "", "0"):
        return None
    try:
        days = int(row["value"])
    except (TypeError, ValueError):
        return None
    return days if days > 0 else None


def set_retention_days(days: Optional[int]) -> None:
    """Persist the retention window. ``None`` or a value <= 0 disables purging.

    Args:
        days: Number of days to keep events, or None/0 to keep forever.

    Raises:
        ValueError: if ``days`` is provided but not a non-negative integer.
    """
    if days is None:
        stored = "0"
    else:
        days = int(days)
        if days < 0:
            raise ValueError("retention days must be >= 0")
        stored = str(days)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_RETENTION_KEY, stored),
        )


def purge_old_events(retention_days: int) -> int:
    """Delete events older than ``retention_days`` days. Return rows removed.

    A ``retention_days`` of 0 or less is treated as "keep forever" and
    deletes nothing.
    """
    if retention_days is None or retention_days <= 0:
        return 0
    cutoff = _utc_cutoff(retention_days)
    with _get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM audit_events WHERE timestamp < ?",
            (cutoff,),
        )
        return cur.rowcount


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
