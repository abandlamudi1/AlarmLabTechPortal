from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
import requests
from werkzeug.datastructures import MultiDict

from services.jira_service import JiraAuthError, JiraService, JiraServiceError
from tools.system_locator import db as systems_db


def _multi_value_form(pairs):
    """Helper to build multi-value form payload for Flask tests."""
    return MultiDict(pairs)


def test_system_creation_and_search_flow(client):
    payload = _multi_value_form([
        ("name", "Alpha Rig"),
        ("location_number", "10-640"),
        ("location_name", "Automation Lab"),
        ("status", "Active"),
        ("notes", "Primary automation bench"),
        ("jira_tickets", "QE-12345"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-123"),
        ("identifier_label", "Login"),
        ("identifier_value", "alpha_login"),
    ])

    response = client.post("/systems/new", data=payload, follow_redirects=True)
    assert response.status_code == 200
    assert b"System Profile created successfully." in response.data

    search_response = client.get(
        f"/systems/?{urlencode({'identifier_type': 'CID', 'identifier_value': 'CID-123'})}"
    )
    assert search_response.status_code == 200
    assert b"Alpha Rig" in search_response.data
    assert b"10-640" in search_response.data
    assert b"Automation Lab" in search_response.data
    assert b"Found 1 system profile" in search_response.data

    # Case-insensitive partial match across identifiers
    partial_response = client.get(
        f"/systems/?{urlencode({'identifier_type': 'Login', 'identifier_value': 'alpha_login'})}"
    )
    assert partial_response.status_code == 200
    assert b"Alpha Rig" in partial_response.data
    assert b"Found 1 system profile" in partial_response.data

    jira_response = client.get(
        f"/systems/?{urlencode({'identifier_type': 'Linked Jira Ticket', 'identifier_value': 'QE-12345'})}"
    )
    assert jira_response.status_code == 200
    assert b"Alpha Rig" in jira_response.data
    assert b"Found 1 system profile" in jira_response.data

    location_response = client.get(
        f"/systems/?{urlencode({'location_name': 'Automation Lab'})}"
    )
    assert location_response.status_code == 200
    assert b"Alpha Rig" in location_response.data
    assert b"Automation Lab" in location_response.data


def test_update_and_delete_system(client):
    system_id = systems_db.create_system(
        {
            "name": "Gamma Rig",
            "location_number": "10-510",
            "location_name": "QE Lab",
            "status": "Active",
            "notes": "Spare system",
            "jira_tickets": "QE-99901\nQE-99902",
        },
        [("CID", "CID-777"), ("Login", "gamma_user")],
    )

    update_payload = _multi_value_form([
        ("name", "Gamma Rig"),
        ("location_number", "10-630"),
        ("location_name", "Product Testing Lab"),
        ("status", "Maintenance"),
        ("notes", "Awaiting parts"),
        ("jira_tickets", "QE-99901\nQE-99902"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-777"),
        ("identifier_label", "MAC"),
        ("identifier_value", "AA:BB:CC:DD:EE:FF"),
    ])

    update_response = client.post(f"/systems/{system_id}/edit", data=update_payload, follow_redirects=True)
    assert update_response.status_code == 200
    assert b"System Profile updated successfully." in update_response.data

    record = systems_db.get_system(system_id)
    assert record is not None
    assert record["status"] == "Maintenance"
    assert record["location_name"] == "Product Testing Lab"
    identifiers = {item["label"]: item["value"] for item in record["identifiers"]}
    assert identifiers["MAC"] == "AA:BB:CC:DD:EE:FF"

    delete_response = client.post(f"/systems/{system_id}/delete", follow_redirects=True)
    assert delete_response.status_code == 200
    assert b"System Profile decommissioned successfully." in delete_response.data
    record_after = systems_db.get_system(system_id)
    assert record_after is not None
    assert record_after["status"] == "Decommissioned"


def test_search_handles_no_results(client):
    response = client.get(
        f"/systems/?{urlencode({'identifier_type': 'CID', 'identifier_value': 'does-not-exist'})}"
    )
    assert response.status_code == 200
    assert b"No system profiles match your filters" in response.data


def test_dashboard_starts_empty(client):
    response = client.get("/systems/")
    assert response.status_code == 200
    assert b"Select an identifier or lab location" in response.data
    assert b"<article class=\"tool-card\">" not in response.data


def test_system_form_validation(client):
    invalid_payload = _multi_value_form([
        ("name", ""),
        ("location_number", ""),
        ("location_name", ""),
        ("status", ""),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-123"),
    ])

    response = client.post("/systems/new", data=invalid_payload)
    assert response.status_code == 400
    assert b"System Profile name is required" in response.data
    assert b"Either Location Number or Location Name is required" in response.data
    assert b"Choose a status" in response.data


def test_duplicate_identifier_rejected(client):
    base = _multi_value_form([
        ("name", "Locator One"),
        ("location_number", "10-510"),
        ("location_name", "QE Lab"),
        ("status", "Active"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-1000"),
    ])
    create_response = client.post("/systems/new", data=base, follow_redirects=True)
    assert create_response.status_code == 200

    duplicate = _multi_value_form([
        ("name", "Locator Two"),
        ("location_number", "10-630"),
        ("location_name", "Product Testing Lab"),
        ("status", "Active"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-1000"),
    ])
    response = client.post("/systems/new", data=duplicate)
    assert response.status_code == 400
    assert b"Already in use" in response.data

    systems = systems_db.search_systems("Locator One")
    base_record = next((item for item in systems if item["name"] == "Locator One"), None)
    assert base_record is not None

    decommission_response = client.post(f"/systems/{base_record['id']}/delete", follow_redirects=True)
    assert decommission_response.status_code == 200

    reuse_payload = _multi_value_form([
        ("name", "Locator Three"),
        ("location_number", "11-050"),
        ("location_name", "DE Lab"),
        ("status", "Active"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-1000"),
    ])
    reuse_response = client.post("/systems/new", data=reuse_payload, follow_redirects=True)
    assert reuse_response.status_code == 200
    assert b"System Profile created successfully." in reuse_response.data


def test_duplicate_identifier_rejected_on_edit(client):
    first_id = systems_db.create_system(
        {
            "name": "Primary Rig",
            "location_number": "9-070",
            "location_name": "International Lab",
            "status": "Active",
            "notes": "",
            "jira_tickets": "",
        },
        [("CID", "CID-9898")],
    )

    second_id = systems_db.create_system(
        {
            "name": "Secondary Rig",
            "location_number": "7-370",
            "location_name": "Commercial Team Lab",
            "status": "Active",
            "notes": "",
            "jira_tickets": "",
        },
        [("CID", "CID-7777")],
    )

    update_payload = _multi_value_form([
        ("name", "Secondary Rig"),
        ("location_number", "7-370"),
        ("location_name", "Commercial Team Lab"),
        ("status", "Active"),
        ("identifier_label", "CID"),
        ("identifier_value", "CID-9898"),
    ])

    response = client.post(f"/systems/{second_id}/edit", data=update_payload)
    assert response.status_code == 400
    assert b"Already in use" in response.data


# ---------------------------------------------------------------------------
# Issue #100: validate_connectivity() unit tests
# ---------------------------------------------------------------------------

_PATCH_JIRA_SERVICE = "tools.system_locator.system_locator_app.JiraService"
_PATCH_TASK = "tools.system_locator.system_locator_app._sync_jira_import_task"


def _mock_jira_service():
    """Return a JiraService with a mock session, bypassing env-var requirements."""
    with patch.dict(
        "os.environ",
        {"JIRA_URL": "https://jira.example.com", "JIRA_PAT": "fake-token"},
    ):
        svc = JiraService()
    svc._session = MagicMock()
    return svc


@pytest.mark.unit
def test_validate_connectivity_success():
    """validate_connectivity() returns None when /myself responds 200."""
    svc = _mock_jira_service()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    svc._session.get.return_value = mock_resp

    svc.validate_connectivity()  # should not raise

    svc._session.get.assert_called_once()
    assert "/rest/api/2/myself" in svc._session.get.call_args[0][0]


@pytest.mark.unit
def test_validate_connectivity_raises_auth_error_on_401():
    """validate_connectivity() raises JiraAuthError for a 401 response."""
    svc = _mock_jira_service()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.ok = False
    svc._session.get.return_value = mock_resp

    with pytest.raises(JiraAuthError):
        svc.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_raises_auth_error_on_403():
    """validate_connectivity() raises JiraAuthError for a 403 response."""
    svc = _mock_jira_service()
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.ok = False
    svc._session.get.return_value = mock_resp

    with pytest.raises(JiraAuthError):
        svc.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_raises_service_error_on_500():
    """validate_connectivity() raises JiraServiceError for a 500 response."""
    svc = _mock_jira_service()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.ok = False
    svc._session.get.return_value = mock_resp

    with pytest.raises(JiraServiceError):
        svc.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_raises_service_error_on_network_failure():
    """validate_connectivity() wraps requests.RequestException in JiraServiceError."""
    svc = _mock_jira_service()
    svc._session.get.side_effect = requests.ConnectionError("unreachable")

    with pytest.raises(JiraServiceError, match="Could not reach Jira"):
        svc.validate_connectivity()


# ---------------------------------------------------------------------------
# Issue #100: pre-flight wiring in jira-import confirm handler
# ---------------------------------------------------------------------------

def test_jira_import_confirm_preflight_fails_shows_form_error_no_dispatch(client):
    """When validate_connectivity raises JiraAuthError, the confirm handler
    appends the error message and does NOT dispatch the Celery task."""
    mock_service = MagicMock()
    mock_service.build_preview.return_value = []

    with patch(_PATCH_JIRA_SERVICE) as MockJiraService, \
         patch(_PATCH_TASK) as mock_task, \
         patch("tools.system_locator.system_locator_app._get_import_service", return_value=mock_service):
        MockJiraService.return_value.validate_connectivity.side_effect = JiraAuthError(
            "Jira authentication failed"
        )
        mock_task.delay.return_value = MagicMock(id="should-not-be-called")

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
    assert b"Jira authentication failed" in resp.data
    mock_task.delay.assert_not_called()


def test_jira_import_confirm_preflight_passes_dispatches_task(client):
    """When validate_connectivity succeeds, the Celery task IS dispatched.

    This is a regression guard: the pre-flight addition must not break the
    happy path that was established in Issue #15 (async dispatch).
    """
    mock_service = MagicMock()
    mock_service.build_preview.return_value = []

    with patch(_PATCH_JIRA_SERVICE) as MockJiraService, \
         patch(_PATCH_TASK) as mock_task, \
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
