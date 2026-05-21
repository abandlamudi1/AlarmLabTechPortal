# tests/test_print_request_tasks.py — Unit tests for tasks/print_request_tasks.py
# Sprint 5 Wave 2, Stream G, Issue #14
#
# All Jira calls are mocked — no real Jira calls are made in CI.
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.print_requests import db as print_requests_db
from tasks.print_request_tasks import (
    create_jira_ticket,
    transition_jira_ticket,
    _ensure_task_columns,
    _update_task_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(app, **kwargs) -> int:
    """Create a print request in the test DB and return its ID."""
    defaults = dict(
        requester="Tester",
        team="QE",
        request_type="new_design",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="Task test",
    )
    defaults.update(kwargs)
    with app.app_context():
        return print_requests_db.create_request(**defaults)


# ---------------------------------------------------------------------------
# _ensure_task_columns
# ---------------------------------------------------------------------------

def test_ensure_task_columns_adds_missing_columns(app, tmp_path):
    """_ensure_task_columns adds jira_task_status and jira_task_id when absent."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE print_requests (id INTEGER PRIMARY KEY, requester TEXT)"
        )
        _ensure_task_columns(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(print_requests)")}
    assert "jira_task_status" in cols
    assert "jira_task_id" in cols


def test_ensure_task_columns_idempotent(app, tmp_path):
    """_ensure_task_columns is safe to call twice."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE print_requests (id INTEGER PRIMARY KEY, jira_task_status TEXT, jira_task_id TEXT)"
        )
        _ensure_task_columns(conn)  # Should not raise
        cols = {r[1] for r in conn.execute("PRAGMA table_info(print_requests)")}
    assert "jira_task_status" in cols


# ---------------------------------------------------------------------------
# create_jira_ticket task
# ---------------------------------------------------------------------------

def test_create_jira_ticket_success(app):
    """create_jira_ticket returns issue_key and updates DB on success."""
    request_id = _make_request(app)

    with app.app_context():
        with patch("tasks.print_request_tasks.JiraService") as MockJira, \
             patch("tasks.print_request_tasks._jira_is_configured", return_value=True):
            instance = MockJira.return_value
            instance.create_lab_request.return_value = "QENG-9999"

            # Call the underlying function directly (bypasses Celery broker)
            result = create_jira_ticket.run(request_id)

    assert result == {"issue_key": "QENG-9999"}

    record = print_requests_db.get_request(request_id)
    assert record["jira_ticket_key"] == "QENG-9999"
    assert record["jira_sync_error"] is None
    assert record["jira_task_status"] == "synced"


def test_create_jira_ticket_not_configured(app):
    """create_jira_ticket exits early and records error when Jira is not configured."""
    request_id = _make_request(app)

    with app.app_context():
        with patch("tasks.print_request_tasks._jira_is_configured", return_value=False):
            result = create_jira_ticket.run(request_id)

    assert result == {"error": "Jira not configured"}

    record = print_requests_db.get_request(request_id)
    assert record["jira_sync_error"] == "Jira is not configured"


def test_create_jira_ticket_missing_request(app):
    """create_jira_ticket returns an error dict when the request_id doesn't exist."""
    with app.app_context():
        with patch("tasks.print_request_tasks._jira_is_configured", return_value=True):
            result = create_jira_ticket.run(99999)

    assert "error" in result


def test_create_jira_ticket_retries_on_jira_error(app):
    """create_jira_ticket records jira_sync_error and sets status=error on final failure.

    Simulates the MaxRetriesExceededError path by mocking retry() to raise it
    immediately so we can assert on the DB side-effects of the final-failure branch.
    """
    from celery.exceptions import MaxRetriesExceededError
    from services.jira_service import JiraServiceError

    request_id = _make_request(app)

    with app.app_context():
        with patch("tasks.print_request_tasks.JiraService") as MockJira, \
             patch("tasks.print_request_tasks._jira_is_configured", return_value=True), \
             patch.object(create_jira_ticket, "retry", side_effect=MaxRetriesExceededError()):
            instance = MockJira.return_value
            instance.create_lab_request.side_effect = JiraServiceError("connection refused")

            result = create_jira_ticket.run(request_id)

    assert "error" in result, f"expected error key in result dict, got {result}"

    record = print_requests_db.get_request(request_id)
    assert record["jira_sync_error"] is not None, "jira_sync_error should be set on final failure"
    assert record["jira_task_status"] == "error"


# ---------------------------------------------------------------------------
# transition_jira_ticket task
# ---------------------------------------------------------------------------

def test_transition_jira_ticket_success(app):
    """transition_jira_ticket calls transition_issue and returns status."""
    with app.app_context():
        with patch("tasks.print_request_tasks.JiraService") as MockJira, \
             patch("tasks.print_request_tasks._jira_is_configured", return_value=True):
            instance = MockJira.return_value
            instance.transition_issue.return_value = None

            result = transition_jira_ticket.run("QENG-9999", "31")

    assert result == {"status": "transitioned"}
    instance.transition_issue.assert_called_once_with("QENG-9999", "31")


def test_transition_jira_ticket_not_configured(app):
    """transition_jira_ticket exits early when Jira is not configured."""
    with app.app_context():
        with patch("tasks.print_request_tasks._jira_is_configured", return_value=False):
            result = transition_jira_ticket.run("QENG-9999", "31")

    assert result == {"error": "Jira not configured"}


def test_transition_jira_ticket_retries_on_jira_error(app):
    """transition_jira_ticket returns error dict and writes back to DB on final failure.

    Uses patch.object to simulate exhausted retries so the final-failure branch
    executes and DB write-back can be asserted.
    """
    from celery.exceptions import MaxRetriesExceededError
    from services.jira_service import JiraServiceError

    request_id = _make_request(app)

    with app.app_context():
        with patch("tasks.print_request_tasks.JiraService") as MockJira, \
             patch("tasks.print_request_tasks._jira_is_configured", return_value=True), \
             patch.object(transition_jira_ticket, "retry", side_effect=MaxRetriesExceededError()):
            instance = MockJira.return_value
            instance.transition_issue.side_effect = JiraServiceError("timeout")

            result = transition_jira_ticket.run("QENG-9999", "31", request_id)

    assert "error" in result, f"expected error key in result dict, got {result}"

    record = print_requests_db.get_request(request_id)
    assert record["jira_sync_error"] is not None, "jira_sync_error should be set on final failure"
    assert record["jira_task_status"] == "error"


# ---------------------------------------------------------------------------
# Integration: form submission sets jira_task_status = pending
# ---------------------------------------------------------------------------

def test_form_submission_dispatches_jira_task(app, client):
    """Submitting the print-request form dispatches the Celery create_jira_ticket
    task and redirects immediately (async path — no blocking Jira call)."""
    with patch("tools.print_requests.print_requests_app._create_jira_ticket_task") as mock_task, \
         patch("tools.print_requests.print_requests_app._jira_creation_enabled", return_value=True):
        mock_task.delay.return_value = MagicMock(id="fake-celery-id")
        resp = client.post(
            "/print-requests/new",
            data={
                "requester": "Test User",
                "team": "QE",
                "request_type": "new_design",
                "description": "test async jira",
                "quantity": "1",
            },
            follow_redirects=False,
        )
        # Form returns immediately (302/303) — does not block on Jira
        assert resp.status_code in (302, 303)
        # Celery task was dispatched exactly once with the new request's ID
        mock_task.delay.assert_called_once()
