"""Persistence helpers for the Checkout tool.

DB path is set at startup via init_app() using DATA_DIR from app config (#2).
SQLite WAL mode + busy timeout applied on every connection (#24).
"""
import os
import sqlite3
from datetime import datetime
from typing import Iterable, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH = os.path.join(BASE_DIR, "checkout.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    checked_out_by TEXT,
    checked_out_at TEXT,
    return_date TEXT,
    jira_link TEXT
)
"""

_DEFAULT_ITEMS: Iterable[str] = (
    "Digital Multimeter",
    "Soldering Station",
    "Oscilloscope",
    "Power Supply",
    "Thermal Camera",
)

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # #24: WAL journal mode for concurrent read safety; busy timeout
    # prevents hard failures when two workers touch the DB simultaneously.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(_SCHEMA)
        _migrate_schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO equipment (name) VALUES (?)",
                ((item,) for item in _DEFAULT_ITEMS),
            )


def _migrate_schema(conn: sqlite3.Connection) -> None:
    columns = [dict(row) for row in conn.execute("PRAGMA table_info(equipment)")]
    column_names = {row["name"] for row in columns}

    if "jira_link" not in column_names:
        conn.execute("ALTER TABLE equipment ADD COLUMN jira_link TEXT")
        column_names.add("jira_link")

    if "return_date" in column_names and "timeframe" not in column_names:
        return

    if "return_date" not in column_names:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_tmp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                checked_out_by TEXT,
                checked_out_at TEXT,
                return_date TEXT,
                jira_link TEXT
            )
            """
        )

        conn.execute(
            "INSERT INTO equipment_tmp(id, name, checked_out_by, checked_out_at, return_date, jira_link)"
            " SELECT id, name, checked_out_by, checked_out_at, NULL, jira_link"
            " FROM equipment"
        )
        conn.execute("DROP TABLE equipment")
        conn.execute("ALTER TABLE equipment_tmp RENAME TO equipment")


def list_equipment() -> List[sqlite3.Row]:
    with _get_connection() as conn:
        return conn.execute(
            "SELECT id, name, checked_out_by, checked_out_at, return_date, jira_link"
            " FROM equipment ORDER BY name"
        ).fetchall()


def checkout_item(item_id: int, user_name: str, return_date: str, jira_link: str) -> bool:
    user_name = user_name.strip()
    jira_link = jira_link.strip()
    normalized_return_date = _normalize_return_date(return_date)

    if not user_name or not normalized_return_date:
        return False

    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT checked_out_by FROM equipment WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None or row["checked_out_by"]:
            return False

        conn.execute(
            "UPDATE equipment SET checked_out_by = ?, checked_out_at = ?, return_date = ?, jira_link = ?"
            " WHERE id = ?",
            (user_name, timestamp, normalized_return_date, jira_link if jira_link else None, item_id),
        )
        return True


def return_item(item_id: int) -> bool:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT checked_out_by FROM equipment WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None or not row["checked_out_by"]:
            return False

        conn.execute(
            "UPDATE equipment SET checked_out_by = NULL, checked_out_at = NULL, return_date = NULL, jira_link = NULL"
            " WHERE id = ?",
            (item_id,),
        )
        return True


def get_item(item_id: int) -> Optional[sqlite3.Row]:
    with _get_connection() as conn:
        return conn.execute(
            "SELECT id, name, checked_out_by, checked_out_at, return_date, jira_link"
            " FROM equipment WHERE id = ?",
            (item_id,),
        ).fetchone()


def _normalize_return_date(value: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.date().isoformat()


def init_app(app) -> None:
    """Wire DATA_DIR into DB_PATH then initialise the schema."""
    global DB_PATH
    data_dir = app.config.get("DATA_DIR", "./data")
    db_dir = os.path.join(data_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "checkout.db")
    init_db()
