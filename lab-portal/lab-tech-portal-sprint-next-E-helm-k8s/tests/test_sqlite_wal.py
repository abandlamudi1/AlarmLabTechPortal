"""Tests that all tool databases are opened in SQLite WAL mode (#24).

Each tool's _get_connection() must execute PRAGMA journal_mode=WAL immediately
after connecting. This test suite verifies the PRAGMA takes effect by querying
journal_mode on a fixture-managed DB.
"""
from __future__ import annotations

import sqlite3

import pytest

from tools.inventory import db as inventory_db
from tools.rf_chamber import db as rf_db
from tools.checkout import db as checkout_db
from tools.system_locator import db as systems_db
from tools.print_requests import db as print_requests_db


def _check_wal(db_path: str) -> str:
    """Open a raw connection and return the journal_mode pragma value."""
    conn = sqlite3.connect(db_path)
    try:
        result = conn.execute("PRAGMA journal_mode").fetchone()
        return result[0] if result else ""
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def isolated_db_paths(tmp_path, monkeypatch):
    """Redirect every tool's DB_PATH to tmp_path for test isolation."""
    monkeypatch.setattr(inventory_db, "DB_PATH", str(tmp_path / "inventory.db"))
    monkeypatch.setattr(rf_db, "DB_PATH", str(tmp_path / "rf_chambers.db"))
    monkeypatch.setattr(checkout_db, "DB_PATH", str(tmp_path / "checkout.db"))
    monkeypatch.setattr(systems_db, "DB_PATH", str(tmp_path / "systems.db"))
    monkeypatch.setattr(print_requests_db, "DB_PATH", str(tmp_path / "print_requests.db"))


def test_inventory_wal(tmp_path):
    """Inventory DB connection activates WAL mode."""
    inventory_db.init_db()
    assert _check_wal(inventory_db.DB_PATH) == "wal"


def test_rf_chamber_wal(tmp_path):
    """RF Chamber DB connection activates WAL mode."""
    rf_db.init_db()
    assert _check_wal(rf_db.DB_PATH) == "wal"


def test_checkout_wal(tmp_path):
    """Checkout DB connection activates WAL mode."""
    checkout_db.init_db()
    assert _check_wal(checkout_db.DB_PATH) == "wal"


def test_system_locator_wal(tmp_path):
    """System Locator DB connection activates WAL mode."""
    systems_db.init_db()
    assert _check_wal(systems_db.DB_PATH) == "wal"


def test_print_requests_wal(tmp_path):
    """Print Requests DB connection activates WAL mode."""
    print_requests_db.init_db()
    assert _check_wal(print_requests_db.DB_PATH) == "wal"
