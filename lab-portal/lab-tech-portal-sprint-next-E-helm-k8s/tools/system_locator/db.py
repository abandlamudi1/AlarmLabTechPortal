"""Persistence helpers for the System Locator tool.

DB path is set at startup via init_app() using DATA_DIR from app config (#2).
SQLite WAL mode + busy timeout applied on every connection (#24).
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH = os.path.join(BASE_DIR, "systems.db")

_SYSTEM_SCHEMA = """
CREATE TABLE IF NOT EXISTS systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    building TEXT,
    room TEXT,
    sub_location TEXT,
    location_number TEXT,
    location_name TEXT,
    status TEXT NOT NULL,
    notes TEXT,
    jira_tickets TEXT,
    jira_issue_key TEXT
)
"""

_IDENTIFIER_SCHEMA = """
CREATE TABLE IF NOT EXISTS identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE
)
"""

_IDENTIFIER_VALUE_INDEX = "CREATE INDEX IF NOT EXISTS idx_identifiers_value ON identifiers(value)"
_SYSTEM_NAME_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_name ON systems(name)"
_SYSTEM_BUILDING_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_building ON systems(building)"
_SYSTEM_ROOM_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_room ON systems(room)"
_SYSTEM_SUBLOCATION_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_sublocation ON systems(sub_location)"
_SYSTEM_LOCATION_NUMBER_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_location_number ON systems(location_number)"
_SYSTEM_LOCATION_NAME_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_location_name ON systems(location_name)"
_SYSTEM_STATUS_INDEX = "CREATE INDEX IF NOT EXISTS idx_systems_status ON systems(status)"
_SYSTEM_JIRA_KEY_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS idx_systems_jira_issue_key ON systems(jira_issue_key)"


@contextmanager
def _get_connection() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # #24: WAL journal mode for concurrent read safety; busy timeout
        # prevents hard failures when two workers touch the DB simultaneously.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(_SYSTEM_SCHEMA)
        conn.execute(_IDENTIFIER_SCHEMA)
        conn.execute(_IDENTIFIER_VALUE_INDEX)
        conn.execute("DROP INDEX IF EXISTS idx_identifiers_value_unique")
        _migrate_schema(conn)  # Run migration first to ensure columns exist
        conn.execute(_SYSTEM_NAME_INDEX)
        conn.execute(_SYSTEM_BUILDING_INDEX)
        conn.execute(_SYSTEM_ROOM_INDEX)
        conn.execute(_SYSTEM_SUBLOCATION_INDEX)
        conn.execute(_SYSTEM_LOCATION_NUMBER_INDEX)
        conn.execute(_SYSTEM_LOCATION_NAME_INDEX)
        conn.execute(_SYSTEM_STATUS_INDEX)
        conn.execute(_SYSTEM_JIRA_KEY_INDEX)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(systems)")}
    if "jira_issue_key" not in columns:
        conn.execute("ALTER TABLE systems ADD COLUMN jira_issue_key TEXT")
    
    # Add new location fields if they don't exist
    if "location_number" not in columns:
        conn.execute("ALTER TABLE systems ADD COLUMN location_number TEXT")
    if "location_name" not in columns:
        conn.execute("ALTER TABLE systems ADD COLUMN location_name TEXT")
    
    # Migrate existing data: building + room -> location_number, sub_location -> location_name
    # Only migrate if location_number is NULL and we have building/room data
    conn.execute("""
        UPDATE systems
        SET location_number = 
            CASE 
                WHEN building IS NOT NULL AND room IS NOT NULL THEN building || '-' || room
                WHEN building IS NOT NULL THEN building
                WHEN room IS NOT NULL THEN room
                ELSE NULL
            END,
            location_name = 
                CASE
                    WHEN sub_location IS NOT NULL AND sub_location != '' THEN sub_location
                    ELSE NULL
                END
        WHERE location_number IS NULL
    """)


def _normalize_identifiers(raw_items: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    cleaned: List[Tuple[str, str]] = []
    for label, value in raw_items:
        normalized_value = (value or "").strip()
        normalized_label = (label or "Identifier").strip() or "Identifier"
        if normalized_value:
            cleaned.append((normalized_label, normalized_value))
    return cleaned


def create_system(data: Dict[str, str], identifiers: Iterable[Tuple[str, str]]) -> int:
    payload = {
        "name": (data.get("name") or "").strip(),
        "building": None,  # Legacy field - no longer used
        "room": None,  # Legacy field - no longer used
        "sub_location": None,  # Legacy field - no longer used
        "location_number": (data.get("location_number") or "").strip() or None,
        "location_name": (data.get("location_name") or "").strip() or None,
        "status": (data.get("status") or "Active").strip() or "Active",
        "notes": (data.get("notes") or "").strip() or None,
        "jira_tickets": _serialize_jira_tickets(data.get("jira_tickets", "")),
        "jira_issue_key": _normalize_jira_key(data.get("jira_issue_key")),
    }

    if not payload["name"]:
        raise ValueError("System name is required")

    normalized_identifiers = _normalize_identifiers(identifiers)

    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO systems (name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key)
            VALUES (:name, :building, :room, :sub_location, :location_number, :location_name, :status, :notes, :jira_tickets, :jira_issue_key)
            """,
            payload,
        )
        system_id = cursor.lastrowid
        _write_identifiers(conn, system_id, normalized_identifiers)
    return int(system_id)


def update_system(system_id: int, data: Dict[str, str], identifiers: Iterable[Tuple[str, str]]) -> None:
    payload = {
        "id": system_id,
        "name": (data.get("name") or "").strip(),
        "building": None,  # Legacy field - no longer used
        "room": None,  # Legacy field - no longer used
        "sub_location": None,  # Legacy field - no longer used
        "location_number": (data.get("location_number") or "").strip() or None,
        "location_name": (data.get("location_name") or "").strip() or None,
        "status": (data.get("status") or "Active").strip() or "Active",
        "notes": (data.get("notes") or "").strip() or None,
        "jira_tickets": _serialize_jira_tickets(data.get("jira_tickets", "")),
        "jira_issue_key": _normalize_jira_key(data.get("jira_issue_key")),
    }

    if not payload["name"]:
        raise ValueError("System name is required")

    normalized_identifiers = _normalize_identifiers(identifiers)

    with _get_connection() as conn:
        conn.execute(
            """
            UPDATE systems
               SET name = :name,
                   building = :building,
                   room = :room,
                   sub_location = :sub_location,
                   location_number = :location_number,
                   location_name = :location_name,
                   status = :status,
                   notes = :notes,
                   jira_tickets = :jira_tickets,
                   jira_issue_key = :jira_issue_key
             WHERE id = :id
            """,
            payload,
        )
        conn.execute("DELETE FROM identifiers WHERE system_id = ?", (system_id,))
        _write_identifiers(conn, system_id, normalized_identifiers)


def delete_system(system_id: int) -> None:
    with _get_connection() as conn:
        conn.execute(
            "UPDATE systems SET status = ? WHERE id = ?",
            ("Decommissioned", system_id),
        )


def hard_delete_system(system_id: int) -> None:
    """Permanently delete a system profile and all its identifiers."""
    with _get_connection() as conn:
        # Foreign key cascade will delete identifiers automatically
        conn.execute("DELETE FROM systems WHERE id = ?", (system_id,))


def get_system(system_id: int) -> Optional[Dict[str, object]]:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key"
            " FROM systems WHERE id = ?",
            (system_id,),
        ).fetchone()
        if row is None:
            return None
        identifiers = conn.execute(
            "SELECT id, label, value FROM identifiers WHERE system_id = ? ORDER BY id",
            (system_id,),
        ).fetchall()

    return {
        "id": row["id"],
        "name": row["name"],
        "building": row["building"],
        "room": row["room"],
        "sub_location": row["sub_location"],
        "location_number": row["location_number"],
        "location_name": row["location_name"],
        "status": row["status"],
        "notes": row["notes"],
        "jira_tickets": _deserialize_jira_tickets(row["jira_tickets"]),
        "jira_issue_key": row["jira_issue_key"],
        "identifiers": [
            {"id": ident["id"], "label": ident["label"], "value": ident["value"]} for ident in identifiers
        ],
    }


def list_systems() -> List[Dict[str, object]]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key"
            " FROM systems ORDER BY name"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_system_by_jira_key(jira_issue_key: str) -> Optional[Dict[str, object]]:
    normalized = _normalize_jira_key(jira_issue_key)
    if not normalized:
        return None
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key"
            " FROM systems WHERE jira_issue_key = ?",
            (normalized,),
        ).fetchone()
    return get_system(row["id"]) if row else None


def find_system_by_identifier(value: str) -> Optional[Dict[str, object]]:
    normalized = (value or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT s.id
              FROM systems s
              JOIN identifiers i ON i.system_id = s.id
             WHERE LOWER(i.value) = ?
          ORDER BY CASE WHEN s.status = 'Decommissioned' THEN 1 ELSE 0 END, s.id
             LIMIT 1
            """,
            (lowered,),
        ).fetchone()
    return get_system(row["id"]) if row else None


def search_systems(term: str) -> List[Dict[str, object]]:
    trimmed = term.strip()
    if not trimmed:
        return list_systems()

    like_term = f"%{trimmed}%"
    with _get_connection() as conn:
        rows = conn.execute(
            """
                        SELECT DISTINCT s.id, s.name, s.building, s.room, s.sub_location, s.location_number, s.location_name, s.status, s.notes, s.jira_tickets, s.jira_issue_key
              FROM systems s
              LEFT JOIN identifiers i ON i.system_id = s.id
             WHERE s.name LIKE ? COLLATE NOCASE
                OR IFNULL(s.building, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.room, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.sub_location, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.location_number, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.location_name, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.status, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.notes, '') LIKE ? COLLATE NOCASE
                OR IFNULL(s.jira_tickets, '') LIKE ? COLLATE NOCASE
                OR IFNULL(i.value, '') LIKE ? COLLATE NOCASE
                OR IFNULL(i.label, '') LIKE ? COLLATE NOCASE
             ORDER BY s.name
            """,
            (like_term, like_term, like_term, like_term, like_term, like_term, like_term, like_term, like_term, like_term, like_term),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_systems_by_identifier(label: str, value: str) -> List[Dict[str, object]]:
    trimmed_label = (label or "").strip()
    trimmed_value = (value or "").strip()
    if not trimmed_label or not trimmed_value:
        return []

    like_value = f"%{trimmed_value}%"
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.id, s.name, s.building, s.room, s.sub_location, s.location_number, s.location_name, s.status, s.notes, s.jira_tickets, s.jira_issue_key
              FROM systems s
              JOIN identifiers i ON i.system_id = s.id
             WHERE LOWER(i.label) = LOWER(?)
               AND LOWER(i.value) LIKE LOWER(?)
             ORDER BY s.name
            """,
            (trimmed_label, like_value),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_systems_by_jira_ticket(value: str) -> List[Dict[str, object]]:
    trimmed_value = (value or "").strip()
    if not trimmed_value:
        return []

    like_value = f"%{trimmed_value}%"
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key
              FROM systems
             WHERE IFNULL(jira_tickets, '') LIKE ? COLLATE NOCASE
                OR IFNULL(jira_issue_key, '') LIKE ? COLLATE NOCASE
             ORDER BY name
            """,
            (like_value, like_value),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_systems_by_location(location_name: str) -> List[Dict[str, object]]:
    trimmed = (location_name or "").strip()
    if not trimmed:
        return []

    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, building, room, sub_location, location_number, location_name, status, notes, jira_tickets, jira_issue_key
              FROM systems
             WHERE LOWER(location_name) = LOWER(?)
             ORDER BY name
            """,
            (trimmed,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_identifiers(system_id: int) -> List[Dict[str, str]]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT label, value FROM identifiers WHERE system_id = ? ORDER BY id",
            (system_id,),
        ).fetchall()
    return [{"label": row["label"], "value": row["value"]} for row in rows]


def get_identifiers_map(system_ids: Iterable[int]) -> Dict[int, List[Dict[str, str]]]:
    ids = [int(system_id) for system_id in system_ids]
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    query = (
        "SELECT system_id, label, value FROM identifiers"
        f" WHERE system_id IN ({placeholders}) ORDER BY system_id, id"
    )

    mapping: Dict[int, List[Dict[str, str]]] = {system_id: [] for system_id in ids}
    with _get_connection() as conn:
        for row in conn.execute(query, ids):
            mapping.setdefault(row["system_id"], []).append({
                "label": row["label"],
                "value": row["value"],
            })
    return mapping


def find_identifier_conflicts(values: Iterable[str], exclude_system_id: Optional[int] = None) -> List[Dict[str, object]]:
    normalized_pairs = [(value.strip(), value.strip().lower()) for value in values if value and value.strip()]
    if not normalized_pairs:
        return []

    lowered_values = [pair[1] for pair in normalized_pairs]
    placeholders = ",".join("?" for _ in lowered_values)
    query = (
        "SELECT i.value, i.label, i.system_id, s.name AS system_name"
        " FROM identifiers i"
        " JOIN systems s ON s.id = i.system_id"
        f" WHERE LOWER(i.value) IN ({placeholders})"
    )
    params: List[object] = lowered_values
    if exclude_system_id is not None:
        query += " AND i.system_id != ?"
        params.append(exclude_system_id)

    query += " AND s.status != 'Decommissioned'"

    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    conflicts: List[Dict[str, object]] = []
    for row in rows:
        conflicts.append({
            "value": row["value"],
            "label": row["label"],
            "system_id": row["system_id"],
            "system_name": row["system_name"],
        })
    return conflicts


def _write_identifiers(conn: sqlite3.Connection, system_id: int, identifiers: Iterable[Tuple[str, str]]) -> None:
    if not identifiers:
        return
    conn.executemany(
        "INSERT INTO identifiers (system_id, label, value) VALUES (?, ?, ?)",
        ((system_id, label, value) for label, value in identifiers),
    )


def _row_to_dict(row: sqlite3.Row) -> Dict[str, object]:
    return {
        "id": row["id"],
        "name": row["name"],
        "building": row["building"],
        "room": row["room"],
        "sub_location": row["sub_location"],
        "location_number": row["location_number"],
        "location_name": row["location_name"],
        "status": row["status"],
        "notes": row["notes"],
        "jira_tickets": _deserialize_jira_tickets(row["jira_tickets"]),
        "jira_issue_key": row["jira_issue_key"],
    }


def _serialize_jira_tickets(value: str) -> Optional[str]:
    tickets = [ticket.strip() for ticket in (value or "").splitlines() if ticket.strip()]
    if not tickets:
        return None
    return "\n".join(tickets)


def _deserialize_jira_tickets(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [ticket for ticket in value.splitlines() if ticket]


def _normalize_jira_key(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip().upper()
    return normalized or None


def init_app(app) -> None:
    """Wire DATA_DIR into DB_PATH then initialise the schema."""
    global DB_PATH
    data_dir = app.config.get("DATA_DIR", "./data")
    db_dir = os.path.join(data_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "systems.db")
    init_db()
