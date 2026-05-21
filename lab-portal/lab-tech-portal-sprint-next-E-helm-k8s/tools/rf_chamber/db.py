"""Persistence helpers for the RF Chamber tool.

Extracted from rf_chamber_app.py as part of Slice D-part1 (#9).
DB path is set at startup via init_app() using DATA_DIR from app config (#2).
SQLite WAL mode + busy timeout applied on every connection (#24).

Note on QR codes: RF Chamber generates QR codes as inline base64 data URIs
(_qr_code_data() in rf_chamber_app.py). No PNG files are written to disk —
this was verified during Sprint 3 footprinting. Issue #47 (QR path
centralisation) therefore does not apply to this tool.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Tuple

# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rf_chambers.db")

# CSV seed file lives alongside the tool source code — it is read-only
# reference data committed to the repo and is not written at runtime.
_DATA_FILE: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "rf_chambers.csv"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chambers (
    barcode TEXT PRIMARY KEY,
    size TEXT,
    ports TEXT,
    purpose TEXT,
    location TEXT,
    owner TEXT
)
"""


@contextmanager
def _get_connection() -> Iterator[sqlite3.Connection]:
    """Open a WAL-mode connection and yield it inside a transaction."""
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


def _normalize(value: str) -> str:
    return value.strip()


def _seed_from_csv(conn: sqlite3.Connection) -> None:
    """Populate chambers table from the bundled CSV seed file (idempotent — INSERT OR IGNORE)."""
    if not os.path.exists(_DATA_FILE):
        return
    with open(_DATA_FILE, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            (
                _normalize(raw.get("Barcodes", "")).upper(),
                _normalize(raw.get("Size", "")),
                _normalize(raw.get("I/O Ports and Accessories", "")),
                _normalize(raw.get("Project/Testing Purpose", "")),
                _normalize(raw.get("Location", "")),
                _normalize(raw.get("Owner", "")),
            )
            for raw in reader
            if _normalize(raw.get("Barcodes", ""))
        ]
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR IGNORE INTO chambers (barcode, size, ports, purpose, location, owner)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def init_db() -> None:
    """Create schema if it does not exist."""
    with _get_connection() as conn:
        conn.execute(_SCHEMA)


def ensure_seeded() -> None:
    """Seed from CSV if the table is empty."""
    with _get_connection() as conn:
        count = conn.execute("SELECT COUNT(1) FROM chambers").fetchone()[0]
        if count == 0:
            _seed_from_csv(conn)


def list_chambers() -> List[Dict[str, str]]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT barcode, size, ports, purpose, location, owner FROM chambers ORDER BY barcode"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def fetch_chamber(barcode: str) -> Optional[Dict[str, str]]:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT barcode, size, ports, purpose, location, owner FROM chambers WHERE barcode = ?",
            (barcode,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def insert_chamber(chamber: Dict[str, str]) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chambers (barcode, size, ports, purpose, location, owner)
            VALUES (:barcode, :size, :ports, :purpose, :location, :owner)
            """,
            chamber,
        )


def update_chamber(original_barcode: str, chamber: Dict[str, str]) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            UPDATE chambers
            SET barcode = :barcode,
                size = :size,
                ports = :ports,
                purpose = :purpose,
                location = :location,
                owner = :owner
            WHERE barcode = :original_barcode
            """,
            {**chamber, "original_barcode": original_barcode},
        )


def delete_chamber(barcode: str) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM chambers WHERE barcode = ?", (barcode,))


def _row_to_dict(row: sqlite3.Row) -> Dict[str, str]:
    return {
        "barcode": row["barcode"],
        "size": row["size"],
        "ports": row["ports"],
        "purpose": row["purpose"],
        "location": row["location"],
        "owner": row["owner"],
    }


def init_app(app) -> None:
    """Wire DATA_DIR into DB_PATH then initialise the schema and seed data.

    Expected sub-directory layout under DATA_DIR (#2):
      db/          — SQLite databases (this tool: rf_chambers.db)
      uploads/     — user-uploaded files (print_requests tool)
      generated/   — app-generated files (inventory QR PNGs, etc.)
    """
    global DB_PATH
    data_dir = app.config.get("DATA_DIR", "./data")
    db_dir = os.path.join(data_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "rf_chambers.db")
    init_db()
    ensure_seeded()
