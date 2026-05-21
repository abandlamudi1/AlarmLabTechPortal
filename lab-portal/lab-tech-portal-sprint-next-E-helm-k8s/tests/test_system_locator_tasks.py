# tests/test_system_locator_tasks.py — Unit tests for tasks/system_locator_tasks.py
# Sprint 5 Wave 2, Stream G, Issue #15
#
# All Jira calls are mocked — no real Jira calls are made in CI.
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tasks.system_locator_tasks import sync_jira_import


# ---------------------------------------------------------------------------
# sync_jira_import task
# ---------------------------------------------------------------------------

def _make_import_result(created=1, updated=0, skipped=0):
    """Build a minimal ImportResult-like mock."""
    result = MagicMock()
    result.created = created
    result.updated = updated
    result.skipped = skipped
    return result


def _make_jira_import_error(message: str):
    """Return a JiraImportError instance for use as a side_effect."""
    from tools.system_locator.jira_import_service import JiraImportError
    return JiraImportError(message)


def _make_jira_permission_error(message: str):
    """Return a JiraPermissionError instance for use as a side_effect."""
    from tools.system_locator.jira_import_service import JiraPermissionError
    return JiraPermissionError(message)


# sync_jira_import now delegates to build_import_service() in system_locator_app.
# build_import_service uses names bound at import time in system_locator_app, so
# patches must target the names as they appear in that module.
_PATCH_JIRA_SERVICE = "tools.system_locator.system_locator_app.JiraService"
_PATCH_JIRA_SERVICE_LOADER = "tools.system_locator.system_locator_app.JiraServiceLoader"
_PATCH_LAB_REQUEST_CLIENT = "tools.system_locator.system_locator_app.LabRequestIngestionClient"
_PATCH_FIELD_MAPPING = "tools.system_locator.system_locator_app.JiraFieldMapping"
_PATCH_IMPORT_SERVICE = "tools.system_locator.system_locator_app.JiraImportService"


def test_sync_jira_import_success(app):
    """sync_jira_import calls service.apply() and returns a summary dict."""
    with app.app_context():
        with patch(_PATCH_JIRA_SERVICE), \
             patch(_PATCH_JIRA_SERVICE_LOADER), \
             patch(_PATCH_LAB_REQUEST_CLIENT), \
             patch(_PATCH_FIELD_MAPPING) as MockMapping, \
             patch(_PATCH_IMPORT_SERVICE) as MockService:
            MockMapping.from_config.return_value = MagicMock()
            mock_service_instance = MockService.return_value
            mock_service_instance.apply.return_value = _make_import_result(
                created=2, updated=1, skipped=0
            )

            result = sync_jira_import.run(
                project_keys=["QENG"],
                start_date_iso=None,
                end_date_iso=None,
                issue_keys=["QENG-100", "QENG-101"],
            )

    assert result == {"created": 2, "updated": 1, "skipped": 0}
    mock_service_instance.apply.assert_called_once()


def test_sync_jira_import_with_dates(app):
    """sync_jira_import correctly parses ISO date strings back to datetime objects."""
    from datetime import datetime

    with app.app_context():
        with patch(_PATCH_JIRA_SERVICE), \
             patch(_PATCH_JIRA_SERVICE_LOADER), \
             patch(_PATCH_LAB_REQUEST_CLIENT), \
             patch(_PATCH_FIELD_MAPPING), \
             patch(_PATCH_IMPORT_SERVICE) as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.apply.return_value = _make_import_result()

            sync_jira_import.run(
                project_keys=None,
                start_date_iso="2026-01-01T00:00:00",
                end_date_iso="2026-03-31T00:00:00",
                issue_keys=None,
            )

    call_kwargs = mock_service_instance.apply.call_args[1]
    assert call_kwargs["start_date"] == datetime(2026, 1, 1, 0, 0, 0)
    assert call_kwargs["end_date"] == datetime(2026, 3, 31, 0, 0, 0)


def test_sync_jira_import_jira_error_returns_error_dict(app):
    """sync_jira_import returns an error dict from production code on JiraImportError.

    Simulates exhausted retries via patch.object so the final-failure branch
    is exercised and the assertion is against the task's actual return value,
    not synthesised in the test.
    """
    from celery.exceptions import MaxRetriesExceededError

    with app.app_context():
        with patch(_PATCH_JIRA_SERVICE), \
             patch(_PATCH_JIRA_SERVICE_LOADER), \
             patch(_PATCH_LAB_REQUEST_CLIENT), \
             patch(_PATCH_FIELD_MAPPING), \
             patch(_PATCH_IMPORT_SERVICE) as MockService, \
             patch.object(sync_jira_import, "retry", side_effect=MaxRetriesExceededError()):
            mock_service_instance = MockService.return_value
            mock_service_instance.apply.side_effect = _make_jira_import_error("Jira unavailable")

            result = sync_jira_import.run(
                project_keys=["QENG"],
                start_date_iso=None,
                end_date_iso=None,
                issue_keys=["QENG-100"],
            )

    assert "error" in result, f"expected error key in result, got {result}"
    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["skipped"] == 0


def test_sync_jira_import_permission_error_returns_error_dict(app):
    """sync_jira_import handles JiraPermissionError the same as JiraImportError."""
    from celery.exceptions import MaxRetriesExceededError

    with app.app_context():
        with patch(_PATCH_JIRA_SERVICE), \
             patch(_PATCH_JIRA_SERVICE_LOADER), \
             patch(_PATCH_LAB_REQUEST_CLIENT), \
             patch(_PATCH_FIELD_MAPPING), \
             patch(_PATCH_IMPORT_SERVICE) as MockService, \
             patch.object(sync_jira_import, "retry", side_effect=MaxRetriesExceededError()):
            mock_service_instance = MockService.return_value
            mock_service_instance.apply.side_effect = _make_jira_permission_error("forbidden")

            result = sync_jira_import.run(
                project_keys=None,
                start_date_iso=None,
                end_date_iso=None,
                issue_keys=["QENG-100"],
            )

    assert "error" in result, f"expected error key in result, got {result}"
    assert "forbidden" in result["error"]


# ---------------------------------------------------------------------------
# Integration: jira-import form dispatches async task
# ---------------------------------------------------------------------------

def test_jira_import_confirm_dispatches_task(app, client):
    """Submitting the jira-import confirm action dispatches a Celery task and
    returns the 'Import in progress...' message instead of blocking.

    Issue #100: JiraService is now patched so the pre-flight validate_connectivity
    call succeeds without real Jira credentials in CI.
    """
    mock_service = MagicMock()
    mock_service.build_preview.return_value = []

    with patch("tools.system_locator.system_locator_app.JiraService") as MockJiraService, \
         patch("tools.system_locator.system_locator_app._sync_jira_import_task") as mock_task, \
         patch("tools.system_locator.system_locator_app._get_import_service", return_value=mock_service):
        MockJiraService.return_value.validate_connectivity.return_value = None
        mock_task.delay.return_value = MagicMock(id="fake-celery-id")

        resp = client.post(
            "/systems/jira-import",
            data={
                "action": "confirm",
                "project_keys": "QENG",
                "confirmed_issue_keys": "QENG-100\nQENG-101",
                "start_date": "",
                "end_date": "",
                "issue_keys": "",
            },
        )

    assert resp.status_code == 200
    assert b"Import in progress" in resp.data
    mock_task.delay.assert_called_once()
