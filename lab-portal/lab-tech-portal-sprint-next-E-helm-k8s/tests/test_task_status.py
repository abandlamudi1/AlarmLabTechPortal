"""Tests for task status tracking: DB migration columns and /api/v1/tasks/<id>/status.

Slice C, Issue #16.

Coverage:
  - _migrate_schema() adds jira_task_status and jira_task_id columns to an
    existing print_requests table that predates them.
  - update_task_status() round-trips values through SQLite.
  - GET /api/v1/tasks/<task_id>/status returns correct JSON for all Celery
    states: PENDING, STARTED, SUCCESS, FAILURE, RETRY.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB migration helpers
# ---------------------------------------------------------------------------


def test_migrate_schema_adds_jira_task_status(tmp_path):
    """jira_task_status column must be present after _migrate_schema() runs."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr.db")
    conn = sqlite3.connect(db_path)
    # Create a minimal print_requests table that lacks the new columns.
    conn.execute(
        """
        CREATE TABLE print_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester TEXT NOT NULL,
            request_type TEXT NOT NULL,
            print_status TEXT NOT NULL DEFAULT 'Design',
            jira_sync_error TEXT,
            jira_ticket_key TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # Run the migration.
    db._migrate_schema(conn)
    conn.commit()

    columns = {row[1] for row in conn.execute("PRAGMA table_info(print_requests)")}
    conn.close()
    assert "jira_task_status" in columns


def test_migrate_schema_adds_jira_task_id(tmp_path):
    """jira_task_id column must be present after _migrate_schema() runs."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr2.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE print_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester TEXT NOT NULL,
            request_type TEXT NOT NULL,
            print_status TEXT NOT NULL DEFAULT 'Design',
            jira_sync_error TEXT,
            jira_ticket_key TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    db._migrate_schema(conn)
    conn.commit()

    columns = {row[1] for row in conn.execute("PRAGMA table_info(print_requests)")}
    conn.close()
    assert "jira_task_id" in columns


def test_migrate_schema_idempotent(tmp_path, monkeypatch):
    """Running _migrate_schema() twice must not raise (idempotent ALTERs)."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr3.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()  # first run creates table + migrates

    conn = sqlite3.connect(db_path)
    # Second run should be a no-op.
    db._migrate_schema(conn)
    conn.commit()
    conn.close()


def test_update_task_status_roundtrip(tmp_path, monkeypatch):
    """update_task_status() must persist task_id and status to the DB."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr4.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()

    request_id = db.create_request(
        requester="Alice",
        team="QE",
        request_type="PLA",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="test",
    )

    db.update_task_status(request_id, task_id="abc-123", status="pending")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT jira_task_id, jira_task_status FROM print_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    conn.close()

    assert row[0] == "abc-123"
    assert row[1] == "pending"


def test_update_task_status_transitions(tmp_path, monkeypatch):
    """Status transitions pending → processing → synced must all persist."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr5.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()

    request_id = db.create_request(
        requester="Bob",
        team="QE",
        request_type="PETG",
        selected_model_details=None,
        quantity=2,
        due_date=None,
        description="transition test",
    )

    for status in ("pending", "processing", "synced"):
        db.update_task_status(request_id, task_id="task-xyz", status=status)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT jira_task_status FROM print_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        conn.close()
        assert row[0] == status


def test_update_task_status_error_state(tmp_path, monkeypatch):
    """update_task_status() with status='error' must be stored correctly."""
    import tools.print_requests.db as db

    db_path = str(tmp_path / "pr6.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()

    request_id = db.create_request(
        requester="Carol",
        team="QE",
        request_type="ABS",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="error test",
    )

    db.update_task_status(request_id, task_id="fail-999", status="error")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT jira_task_id, jira_task_status FROM print_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    conn.close()

    assert row[0] == "fail-999"
    assert row[1] == "error"


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/<task_id>/status — endpoint tests
# ---------------------------------------------------------------------------


def _make_async_result(state: str, result=None, *, failed: bool = False, successful: bool = False):
    """Build a mock Celery AsyncResult with the given state and result."""
    mock_result = MagicMock()
    mock_result.state = state
    mock_result.result = result
    mock_result.successful.return_value = successful
    mock_result.failed.return_value = failed
    return mock_result


def test_task_status_pending(client):
    """PENDING state returns state=PENDING, result=null, error=null."""
    mock_ar = _make_async_result("PENDING")
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/test-task-id/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["task_id"] == "test-task-id"
    assert data["state"] == "PENDING"
    assert data["result"] is None
    assert data["error"] is None


def test_task_status_success(client):
    """SUCCESS state returns result payload and error=null."""
    success_payload = {"jira_key": "LAB-42"}
    mock_ar = _make_async_result("SUCCESS", result=success_payload, successful=True)
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/success-task/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "SUCCESS"
    assert data["result"] == success_payload
    assert data["error"] is None


def test_task_status_failure(client):
    """FAILURE state returns error string and result=null."""
    exc = RuntimeError("Jira API timeout")
    mock_ar = _make_async_result("FAILURE", result=exc, failed=True)
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/fail-task/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "FAILURE"
    assert data["result"] is None
    assert "Jira API timeout" in data["error"]


def test_task_status_started(client):
    """STARTED state returns state=STARTED, result=null, error=null."""
    mock_ar = _make_async_result("STARTED")
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/started-task/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "STARTED"
    assert data["result"] is None
    assert data["error"] is None


def test_task_status_retry(client):
    """RETRY state returns state=RETRY, result=null, error=null."""
    mock_ar = _make_async_result("RETRY")
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/retry-task/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "RETRY"
    assert data["result"] is None
    assert data["error"] is None


def test_task_status_returns_json_content_type(client):
    """Response must have Content-Type application/json."""
    mock_ar = _make_async_result("PENDING")
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/any-task/status")

    assert "application/json" in resp.content_type


def test_task_status_includes_task_id_in_response(client):
    """The task_id field in the response must echo the URL parameter."""
    mock_ar = _make_async_result("PENDING")
    mock_celery = MagicMock()
    mock_celery.AsyncResult.return_value = mock_ar

    with patch.dict("sys.modules", {"app": MagicMock(celery=mock_celery)}):
        resp = client.get("/api/v1/tasks/my-unique-uuid-1234/status")

    data = resp.get_json()
    assert data["task_id"] == "my-unique-uuid-1234"
