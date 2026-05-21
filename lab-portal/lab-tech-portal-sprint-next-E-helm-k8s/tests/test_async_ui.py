"""Tests for Issue #18 — async Jira status badges and polling UI.

Covers:
- Print request detail page: pending badge when jira_task_status == 'pending'
- Print request detail page: polling script injected when task is in-flight
- Print request detail page: error state shows retry button
- Print request retry endpoint: re-dispatches task and redirects
- System locator Jira import: task_id present in response when action == 'confirm'
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.print_requests import db as print_requests_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_print_request(app, **kwargs) -> int:
    defaults = dict(
        requester="Tester",
        team="QE",
        request_type="new_design",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="Async UI test request",
    )
    defaults.update(kwargs)
    with app.app_context():
        return print_requests_db.create_request(**defaults)


# ---------------------------------------------------------------------------
# Print request detail — async Jira status rendering
# ---------------------------------------------------------------------------


def test_detail_shows_pending_badge_when_task_pending(client, app):
    """When jira_task_status is 'pending', detail page shows 'Jira ticket pending...'."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="task-abc-123", status="pending")

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Jira ticket pending..." in body


def test_detail_shows_pending_badge_when_task_processing(client, app):
    """When jira_task_status is 'processing', detail page shows pending badge."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="task-proc-456", status="processing")

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Jira ticket pending..." in body


def test_detail_injects_polling_script_when_task_pending(client, app):
    """Polling script must be present on detail page when jira_task_status is 'pending'."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="poll-task-789", status="pending")

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    # The task ID must appear in the rendered JS for polling to work
    assert "poll-task-789" in body
    assert "/api/v1/tasks/" in body
    assert "setInterval" in body


def test_detail_shows_no_polling_script_when_synced(client, app):
    """When jira_task_status is 'synced', no polling script should be injected."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="done-task-001", status="synced")
        print_requests_db.update_jira_status(
            request_id, jira_ticket_key="LAB-100", jira_sync_error=None
        )

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "setInterval" not in body
    assert "LAB-100" in body


def test_detail_shows_error_state_with_retry_button(client, app):
    """When jira_task_status is 'error', detail page shows error message and retry button."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="err-task-999", status="error")
        print_requests_db.update_jira_status(
            request_id, jira_ticket_key=None, jira_sync_error="Jira API timeout"
        )

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Jira API timeout" in body
    assert "Retry Jira sync" in body
    assert "retry-jira" in body


def test_detail_shows_not_yet_created_when_no_task(client, app):
    """When jira_task_status is None and no ticket key, shows 'Not yet created'."""
    request_id = _create_print_request(app)
    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Not yet created" in body


# ---------------------------------------------------------------------------
# Print request detail — retry endpoint
# ---------------------------------------------------------------------------


def test_retry_endpoint_redispatches_task_on_error(client, app):
    """POST /requests/<id>/retry-jira re-dispatches the Celery task when in error state."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="err-task-retry", status="error")
        print_requests_db.update_jira_status(
            request_id, jira_ticket_key=None, jira_sync_error="Connection refused"
        )

    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id="new-task-id")

    with patch(
        "tools.print_requests.print_requests_app._create_jira_ticket_task",
        mock_task,
    ):
        response = client.post(
            f"/print-requests/requests/{request_id}/retry-jira",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert f"/requests/{request_id}" in response.headers["Location"]
    mock_task.delay.assert_called_once_with(request_id)


def test_retry_endpoint_resets_status_to_pending(client, app):
    """POST /requests/<id>/retry-jira sets jira_task_status to 'pending' before dispatching."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="err-task-reset", status="error")
        print_requests_db.update_jira_status(
            request_id, jira_ticket_key=None, jira_sync_error="Timeout"
        )

    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id="reset-task-id")

    with patch(
        "tools.print_requests.print_requests_app._create_jira_ticket_task",
        mock_task,
    ):
        client.post(f"/print-requests/requests/{request_id}/retry-jira")

    with app.app_context():
        record = print_requests_db.get_request(request_id)
    assert record["jira_task_status"] == "pending"


def test_retry_endpoint_is_noop_when_not_in_error(client, app):
    """POST /requests/<id>/retry-jira does NOT dispatch when request is not in error state."""
    request_id = _create_print_request(app)
    with app.app_context():
        print_requests_db.update_task_status(request_id, task_id="ok-task-id", status="synced")
        print_requests_db.update_jira_status(
            request_id, jira_ticket_key="LAB-200", jira_sync_error=None
        )

    mock_task = MagicMock()

    with patch(
        "tools.print_requests.print_requests_app._create_jira_ticket_task",
        mock_task,
    ):
        response = client.post(
            f"/print-requests/requests/{request_id}/retry-jira",
            follow_redirects=False,
        )

    assert response.status_code == 302
    mock_task.delay.assert_not_called()


def test_retry_endpoint_returns_404_for_missing_request(client):
    """POST /requests/99999/retry-jira returns 404 if request does not exist."""
    response = client.post("/print-requests/requests/99999/retry-jira")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# System locator Jira import — task ID surfacing
# ---------------------------------------------------------------------------


def _patch_import_service():
    """Context manager patching _get_import_service so it returns a safe mock.

    Also patches JiraService so the pre-flight validate_connectivity call
    (Issue #100) succeeds without real Jira credentials in CI.
    """
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        mock_service = MagicMock()
        mock_service.build_preview.return_value = []
        with patch(
            "tools.system_locator.system_locator_app._get_import_service",
            return_value=mock_service,
        ), patch(
            "tools.system_locator.system_locator_app.JiraService"
        ) as MockJiraService:
            MockJiraService.return_value.validate_connectivity.return_value = None
            yield

    return _cm()


def test_jira_import_confirm_includes_task_id_in_response(client, app):
    """After confirm POST, rendered HTML must include the Celery task ID."""
    mock_task = MagicMock()
    fake_task_id = "celery-import-task-abc"
    mock_task.delay.return_value = MagicMock(id=fake_task_id)

    with _patch_import_service(), patch(
        "tools.system_locator.system_locator_app._sync_jira_import_task",
        mock_task,
    ):
        response = client.post(
            "/systems/jira-import",
            data={
                "action": "confirm",
                "confirmed_issue_keys": "QEPR-101\nQEOPS-55",
                "project_keys": "",
                "start_date": "",
                "end_date": "",
            },
            follow_redirects=False,
        )

    assert response.status_code == 200
    body = response.data.decode()
    assert fake_task_id in body


def test_jira_import_confirm_shows_in_progress_message(client, app):
    """After confirm POST, the 'Import in progress' message must be visible."""
    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id="celery-progress-task")

    with _patch_import_service(), patch(
        "tools.system_locator.system_locator_app._sync_jira_import_task",
        mock_task,
    ):
        response = client.post(
            "/systems/jira-import",
            data={
                "action": "confirm",
                "confirmed_issue_keys": "QEPR-202",
                "project_keys": "",
                "start_date": "",
                "end_date": "",
            },
        )

    assert response.status_code == 200
    body = response.data.decode()
    assert "Import in progress" in body


def test_jira_import_confirm_polling_script_injected(client, app):
    """After confirm POST, the polling JS referencing the task ID must be present."""
    fake_task_id = "poll-import-task-xyz"
    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id=fake_task_id)

    with _patch_import_service(), patch(
        "tools.system_locator.system_locator_app._sync_jira_import_task",
        mock_task,
    ):
        response = client.post(
            "/systems/jira-import",
            data={
                "action": "confirm",
                "confirmed_issue_keys": "QEPR-303",
                "project_keys": "",
                "start_date": "",
                "end_date": "",
            },
        )

    assert response.status_code == 200
    body = response.data.decode()
    assert fake_task_id in body
    assert "setInterval" in body
    assert "/api/v1/tasks/" in body


def test_jira_import_preview_does_not_show_task_id(client, app):
    """GET (preview) request to jira-import must not show any task ID or polling JS."""
    with _patch_import_service():
        response = client.get("/systems/jira-import")
    assert response.status_code == 200
    body = response.data.decode()
    assert "setInterval" not in body
    assert "import-status-block" not in body
