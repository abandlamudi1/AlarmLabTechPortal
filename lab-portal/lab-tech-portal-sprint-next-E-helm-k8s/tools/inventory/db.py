"""Persistence helpers for the Inventory tool.

Extracted from inventory_app.py as part of Slice D-part1 (#9).
DB path is set at startup via init_app() using DATA_DIR from app config (#2).
SQLite WAL mode + busy timeout applied on every connection (#24).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional

# Module-level path; overridden by init_app() at startup so tests can
# monkeypatch this attribute to redirect writes to tmp_path.
DB_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    quantity INTEGER,
    min_stock INTEGER,
    qr_code TEXT
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


def init_db() -> None:
    """Create schema if it does not exist."""
    with _get_connection() as conn:
        conn.execute(_SCHEMA)


def get_items() -> List[Dict[str, object]]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, quantity, min_stock, qr_code FROM items"
        ).fetchall()

    items = []
    for row in rows:
        qr_code = (row["qr_code"] or "").replace("\\", "/")
        # Normalise legacy paths that were stored with a "static/" prefix.
        if qr_code.startswith("static/"):
            qr_code = qr_code.split("/", 1)[1] if "/" in qr_code else qr_code
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "quantity": row["quantity"],
                "min_stock": row["min_stock"],
                "qr_code": qr_code,
            }
        )
    return items


def add_item(
    name: str,
    description: str,
    quantity: int,
    min_stock: int,
) -> int:
    """Insert a new item and return its id."""
    with _get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO items(name, description, quantity, min_stock) VALUES(?,?,?,?)",
            (name, description, quantity, min_stock),
        )
        return int(cur.lastrowid)


def set_qr_code(item_id: int, qr_filename: str) -> None:
    """Store the QR code filename (relative to DATA_DIR/generated/inventory/) for an item."""
    with _get_connection() as conn:
        conn.execute("UPDATE items SET qr_code=? WHERE id=?", (qr_filename, item_id))


def update_quantity(item_id: int, change: int) -> None:
    """Atomically adjust quantity by *change* (positive or negative)."""
    with _get_connection() as conn:
        conn.execute(
            "UPDATE items SET quantity = quantity + ? WHERE id=?",
            (change, item_id),
        )


def get_item(item_id: int) -> Optional[Dict[str, object]]:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, quantity, min_stock, qr_code FROM items WHERE id=?",
            (item_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def init_app(app) -> None:
    """Wire DATA_DIR into DB_PATH then initialise the schema.

    Expected sub-directory layout under DATA_DIR (#2):
      db/          — SQLite databases (this tool: inventory.db)
      uploads/     — user-uploaded files (print_requests tool)
      generated/   — app-generated files (inventory QR PNGs, etc.)
    """
    global DB_PATH
    data_dir = app.config.get("DATA_DIR", "./data")
    db_dir = os.path.join(data_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "inventory.db")
    init_db()
