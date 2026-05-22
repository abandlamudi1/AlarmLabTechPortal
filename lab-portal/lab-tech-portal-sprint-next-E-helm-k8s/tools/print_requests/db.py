"""Persistence helpers for 3D print requests.

DB path is set at startup via init_app() using DATA_DIR from app config (#2).
SQLite WAL mode + busy timeout applied on every connection (#24).

Upload path convention (#3):
  Values stored in uploaded_file_path and uploaded_image_path are *relative*
  paths under the uploads root, NOT absolute filesystem paths. Concrete shapes:
    - uploaded_file_path:  "<uuid>_<secure_filename>"
    - uploaded_image_path: "design_images/<uuid>_<secure_filename>"
  Callers resolve them with os.path.join(DATA_DIR, "uploads", relative_path).
  Use .scripts/migrate_print_request_paths.py to convert legacy absolute paths.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

# Python 3.11 compatibility: UTC moved from datetime module to timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH = os.path.join(BASE_DIR, "print_requests.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS print_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester TEXT NOT NULL,
    team TEXT,
    request_type TEXT NOT NULL,
    selected_model_details TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    due_date TEXT,
    description TEXT,
    uploaded_file_path TEXT,
    uploaded_image_path TEXT,
    print_status TEXT NOT NULL DEFAULT 'Design',
    jira_sync_error TEXT,
    jira_ticket_key TEXT,
    created_at TEXT NOT NULL
)
"""

_INDEX_CREATED_AT = "CREATE INDEX IF NOT EXISTS idx_print_requests_created_at ON print_requests(created_at DESC)"
_INDEX_JIRA_KEY = "CREATE INDEX IF NOT EXISTS idx_print_requests_jira_key ON print_requests(jira_ticket_key)"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # #24: WAL journal mode for concurrent read safety; busy timeout
        # prevents hard failures when two workers touch the DB simultaneously.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)
        conn.execute(_INDEX_CREATED_AT)
        conn.execute(_INDEX_JIRA_KEY)
        _migrate_schema(conn)


def create_request(
    *,
    requester: str,
    team: str,
    request_type: str,
    selected_model_details: Optional[Dict[str, str]],
    quantity: int,
    due_date: Optional[str],
    description: str,
    uploaded_file_path: Optional[str] = None,
    uploaded_image_path: Optional[str] = None,
    print_status: str = "Design",
    jira_sync_error: Optional[str] = None,
    jira_ticket_key: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> int:
    payload = {
        "requester": requester.strip(),
        "team": team.strip() or None,
        "request_type": request_type.strip(),
        "selected_model_details": _serialize_selected_model(selected_model_details),
        "quantity": max(int(quantity or 1), 1),
        "due_date": (due_date or "").strip() or None,
        "description": (description or "").strip() or None,
        "uploaded_file_path": uploaded_file_path,
        "uploaded_image_path": uploaded_image_path,
        "print_status": (print_status or "Design").strip() or "Design",
        "jira_sync_error": (jira_sync_error or "").strip() or None,
        "jira_ticket_key": (jira_ticket_key or "").strip() or None,
        "created_at": (created_at or datetime.now(UTC)).isoformat(timespec="seconds"),
    }

    if not payload["requester"]:
        raise ValueError("Requester name is required")
    if not payload["request_type"]:
        raise ValueError("Request type is required")

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO print_requests (
                requester,
                team,
                request_type,
                selected_model_details,
                quantity,
                due_date,
                description,
                uploaded_file_path,
                uploaded_image_path,
                print_status,
                jira_sync_error,
                jira_ticket_key,
                created_at
            ) VALUES (
                :requester,
                :team,
                :request_type,
                :selected_model_details,
                :quantity,
                :due_date,
                :description,
                :uploaded_file_path,
                :uploaded_image_path,
                :print_status,
                :jira_sync_error,
                :jira_ticket_key,
                :created_at
            )
            """,
            payload,
        )
        return int(cursor.lastrowid)


def list_requests() -> List[Dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, requester, team, request_type, selected_model_details, quantity, due_date,"
            " description, uploaded_file_path, uploaded_image_path, print_status,"
            " jira_sync_error, jira_ticket_key, created_at, jira_task_status, jira_task_id"
            " FROM print_requests ORDER BY datetime(created_at) DESC, id DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def pending_requests() -> List[Dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, requester, team, request_type, selected_model_details, quantity, due_date,"
            " description, uploaded_file_path, uploaded_image_path, print_status,"
            " jira_sync_error, jira_ticket_key, created_at, jira_task_status, jira_task_id"
            " FROM print_requests WHERE jira_ticket_key IS NULL AND print_status NOT IN ('Cancelled', 'Closed')"
            " ORDER BY datetime(created_at)"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def mark_synced(request_id: int, jira_ticket_key: str) -> None:
    key = jira_ticket_key.strip().upper()
    if not key:
        raise ValueError("jira_ticket_key must be non-empty")
    with _connect() as conn:
        conn.execute(
            "UPDATE print_requests SET jira_ticket_key = ?, jira_sync_error = NULL WHERE id = ?",
            (key, request_id),
        )


def update_jira_status(request_id: int, *, jira_ticket_key: Optional[str], jira_sync_error: Optional[str]) -> None:
    key = (jira_ticket_key or "").strip().upper() or None
    error = (jira_sync_error or "").strip() or None
    with _connect() as conn:
        conn.execute(
            "UPDATE print_requests SET jira_ticket_key = ?, jira_sync_error = ? WHERE id = ?",
            (key, error, request_id),
        )


def update_print_status(request_id: int, print_status: str) -> None:
    status = (print_status or "").strip() or "Design"
    with _connect() as conn:
        conn.execute(
            "UPDATE print_requests SET print_status = ? WHERE id = ?",
            (status, request_id),
        )


def get_request(request_id: int) -> Optional[Dict[str, object]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, requester, team, request_type, selected_model_details, quantity, due_date,"
            " description, uploaded_file_path, uploaded_image_path, print_status,"
            " jira_sync_error, jira_ticket_key, created_at, jira_task_status, jira_task_id"
            " FROM print_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, object]:
    keys = row.keys()
    result = {
        "id": row["id"],
        "requester": row["requester"],
        "team": row["team"],
        "request_type": row["request_type"],
        "selected_model_details": _deserialize_selected_model(row["selected_model_details"]),
        "quantity": row["quantity"],
        "due_date": row["due_date"],
        "description": row["description"],
        "uploaded_file_path": row["uploaded_file_path"],
        "uploaded_image_path": row["uploaded_image_path"],
        "print_status": row["print_status"],
        "jira_sync_error": row["jira_sync_error"],
        "jira_ticket_key": row["jira_ticket_key"],
        "created_at": row["created_at"],
        # Wave 2 Stream H adds these columns; read defensively so existing
        # rows and pre-H schema do not raise KeyError.
        "jira_task_status": row["jira_task_status"] if "jira_task_status" in keys else None,
        "jira_task_id": row["jira_task_id"] if "jira_task_id" in keys else None,
    }
    return result


def _serialize_selected_model(details: Optional[Dict[str, str]]) -> Optional[str]:
    if not details:
        return None
    cleaned = {key: value for key, value in details.items() if value}
    if not cleaned:
        return None
    return json.dumps(cleaned, sort_keys=True)


def _deserialize_selected_model(payload: Optional[str]) -> Dict[str, str]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items() if value is not None}
    except json.JSONDecodeError:
        return {}
    return {}


def _migrate_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(print_requests)")}
    if "selected_model_details" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN selected_model_details TEXT")
    if "quantity" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
    if "due_date" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN due_date TEXT")
    if "uploaded_image_path" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN uploaded_image_path TEXT")
    if "print_status" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN print_status TEXT NOT NULL DEFAULT 'Design'")
    if "jira_sync_error" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN jira_sync_error TEXT")
    # Wave 2 Stream H adds these; also added here so the columns exist from
    # Stream G's migration so SELECT queries can include them safely.
    if "jira_task_status" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN jira_task_status TEXT")
    if "jira_task_id" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN jira_task_id TEXT")


def update_task_status(request_id: int, *, task_id: str, status: str) -> None:
    """Update jira_task_id and jira_task_status for a print request.

    Called by Celery task dispatch (set status='pending' + task UUID) and by
    task result callbacks (set status='processing'/'synced'/'error').
    """
    with _connect() as conn:
        conn.execute(
            "UPDATE print_requests SET jira_task_id = ?, jira_task_status = ? WHERE id = ?",
            (task_id, status, request_id),
        )


def init_app(app) -> None:
    """Wire DATA_DIR into DB_PATH then initialise the schema."""
    global DB_PATH
    data_dir = app.config.get("DATA_DIR", "./data")
    db_dir = os.path.join(data_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "print_requests.db")
    init_db()
