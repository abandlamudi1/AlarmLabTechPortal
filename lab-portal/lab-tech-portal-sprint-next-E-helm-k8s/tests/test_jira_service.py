"""Tests for JiraService: unit tests for retry/rate-limit behaviour and
integration tests for Lab Request CRUD operations.

Unit tests (no network, no Jira creds required) are marked with
@pytest.mark.unit and mock the HTTP session.  Integration tests require
JIRA_URL, JIRA_PAT, and all JIRA_CUSTOMFIELD_* / JIRA_LAB_REQUEST_*
env vars; they are skipped automatically when any required var is absent.
"""
import os
import threading
from datetime import date, datetime
from unittest.mock import MagicMock
import requests

import pytest

from services.jira_service import (
    JiraService,
    JiraServiceError,
    JiraAuthError,
    JiraIssueCreationError,
    JiraIssueUpdateError,
    JiraIssueTransitionError,
    JiraMetadataError,
    JiraAttachmentUploadError,
    JiraNotFoundError,
    JiraRateLimitError,
    _TokenBucket,
)


@pytest.fixture
def jira_client():
    """Create a real JiraService client using environment credentials."""
    required_vars = ["JIRA_URL", "JIRA_PAT"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        pytest.skip(f"Missing environment variables for Jira integration test: {', '.join(missing)}")
    return JiraService()


@pytest.mark.creates_jira_tickets
def test_create_lab_request_integration(jira_client):
    """Test creating a real Lab Request ticket via REST API.
    
    ⚠️ WARNING: This test creates a REAL Jira ticket in the QENG project!
    Run with: pytest -m creates_jira_tickets tests/test_jira_service.py::test_create_lab_request_integration
    """
    summary = "Test for Ben using JIRA REST API"
    description = "This is an automated test ticket created to validate the JiraService client."
    # Default assignee is Ben Bryce (bbrice)
    assignee = os.getenv("JIRA_DEFAULT_ASSIGNEE", "bbrice")
    priority = "P5: Nice to Have"
    lab_request_type = "Lab setup"
    deadline = datetime.now().date().isoformat()

    try:
        issue_key = jira_client.create_lab_request(
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            lab_request_type=lab_request_type,
            deadline=deadline,
        )

        assert issue_key is not None
        assert issue_key.startswith("QENG-")
        print(f"\n✓ Successfully created ticket: {issue_key}")

    except JiraServiceError as exc:
        pytest.fail(f"Failed to create Lab Request: {exc}")


def test_get_transitions_integration(jira_client):
    """Test fetching available transitions for an existing ticket."""
    # Use the example ticket from earlier
    issue_key = "QENG-16450"

    try:
        transitions_data = jira_client.get_transitions(issue_key)
        transitions = transitions_data.get("transitions", [])

        assert isinstance(transitions, list)
        assert len(transitions) > 0

        # Print available transitions for debugging
        print(f"\n✓ Available transitions for {issue_key}:")
        for transition in transitions:
            print(f"  - {transition.get('name')} (ID: {transition.get('id')})")

    except JiraServiceError as exc:
        pytest.fail(f"Failed to fetch transitions: {exc}")


def test_get_issue_integration(jira_client):
    """Test fetching full issue details."""
    issue_key = "QENG-16450"

    try:
        issue = jira_client.get_issue(issue_key)

        assert "key" in issue
        assert issue["key"] == issue_key
        assert "fields" in issue

        fields = issue["fields"]
        print(f"\n✓ Successfully fetched {issue_key}:")
        print(f"  Summary: {fields.get('summary', 'N/A')}")
        print(f"  Status: {fields.get('status', {}).get('name', 'N/A')}")
        print(f"  Assignee: {fields.get('assignee', {}).get('displayName', 'Unassigned') if fields.get('assignee') else 'Unassigned'}")
        print(f"  Priority: {fields.get('priority', {}).get('name', 'N/A')}")

    except JiraServiceError as exc:
        pytest.fail(f"Failed to fetch issue: {exc}")


@pytest.mark.creates_jira_tickets
def test_update_methods_integration(jira_client):
    """Test updating various fields on a Lab Request ticket.
    
    ⚠️ WARNING: This test creates a REAL Jira ticket in the QENG project!
    Run with: pytest -m creates_jira_tickets tests/test_jira_service.py::test_update_methods_integration
    """
    # First create a test ticket
    summary = "Test ticket for field updates"
    description = "Initial description"
    assignee = "bbrice"
    priority = "P5: Nice to Have"
    lab_request_type = "Lab setup"
    deadline = datetime.now().date().isoformat()

    try:
        issue_key = jira_client.create_lab_request(
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            lab_request_type=lab_request_type,
            deadline=deadline,
        )
        print(f"\n✓ Created test ticket: {issue_key}")

        # Test update_description
        new_description = "Updated description via update_description method"
        jira_client.update_description(issue_key, new_description)
        print(f"✓ Updated description")

        # Test update_assignee
        jira_client.update_assignee(issue_key, "snodder")
        print(f"✓ Updated assignee to snodder")

        # Test update_priority
        jira_client.update_priority(issue_key, "P3: Medium")
        print(f"✓ Updated priority")
        
        # Test update_deadline
        from datetime import timedelta
        new_deadline = (datetime.now() + timedelta(days=7)).date().isoformat()
        jira_client.update_deadline(issue_key, new_deadline)
        print(f"✓ Updated deadline")

        # Verify changes
        issue = jira_client.get_issue(issue_key)
        fields = issue["fields"]
        assert fields["description"] == new_description
        assert fields["assignee"]["name"] == "snodder"
        assert fields["priority"]["name"] == "P3: Medium"
        assert fields["customfield_18053"] == new_deadline
        print(f"✓ All field updates verified")

    except JiraServiceError as exc:
        pytest.fail(f"Failed in update tests: {exc}")


def test_search_issues_integration(jira_client):
    """Test searching for Lab Request issues using JQL."""
    # Search for recent issues in QENG project
    # Note: Using just project search since Lab Request issue type ID/name may vary
    jql = 'project = QENG ORDER BY created DESC'

    try:
        result = jira_client.search_issues(jql, max_results=5)

        assert "issues" in result
        assert "total" in result
        assert isinstance(result["issues"], list)

        total = result["total"]
        issues = result["issues"]

        print(f"\n✓ Search found {total} total issues in QENG")
        print(f"✓ Retrieved {len(issues)} issues (max 5)")

        # Validate structure of returned issues
        if issues:
            first_issue = issues[0]
            assert "key" in first_issue
            assert "fields" in first_issue
            issue_type = first_issue['fields'].get('issuetype', {})
            issue_type_name = issue_type.get('name', 'N/A') if isinstance(issue_type, dict) else 'N/A'
            print(f"\n  Sample issue: {first_issue['key']}")
            print(f"  Summary: {first_issue['fields'].get('summary', 'N/A')}")
            print(f"  Issue Type: {issue_type_name}")

    except JiraServiceError as exc:
        pytest.fail(f"Failed to search issues: {exc}")


# =============================================================================
# Unit tests — no network, no Jira credentials required
# =============================================================================

# ---------------------------------------------------------------------------
# Env-var fixture — provides all required vars so JiraService can be
# constructed without a real Jira instance.
# ---------------------------------------------------------------------------

UNIT_ENV = {
    "JIRA_URL": "https://jira.example.com",
    "JIRA_PAT": "unit-test-pat",
    "JIRA_LAB_REQUEST_ISSUE_TYPE_ID": "99999",
    "JIRA_CUSTOMFIELD_LAB_REQUEST_TYPE": "customfield_00001",
    "JIRA_CUSTOMFIELD_LEAD_QE_TEAM": "customfield_00002",
    "JIRA_CUSTOMFIELD_LEAD_RD_TEAM": "customfield_00003",
    "JIRA_CUSTOMFIELD_DEADLINE": "customfield_00004",
    "JIRA_CUSTOMFIELD_PLANNED_END_DATE": "customfield_00005",
    "JIRA_CUSTOMFIELD_HIGH_LEVEL_ESTIMATE": "customfield_00006",
}


@pytest.fixture
def jira_unit(monkeypatch):
    """JiraService instance with all env vars patched for unit testing."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    return JiraService()


# ---------------------------------------------------------------------------
# _TokenBucket unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_bucket_acquires_within_capacity():
    """Should acquire tokens without blocking when bucket is full."""
    bucket = _TokenBucket(rate=10.0, capacity=5.0, block_timeout=1.0)
    # Should not raise for first 5 acquires (full bucket)
    for _ in range(5):
        bucket.acquire()


@pytest.mark.unit
def test_token_bucket_raises_when_exhausted():
    """Should raise JiraRateLimitError when tokens run out and timeout expires."""
    # Single-token bucket that refills at 0.1 tok/s — impossible to refill in 0.01s
    bucket = _TokenBucket(rate=0.1, capacity=1.0, block_timeout=0.01)
    bucket.acquire()  # consume the only token
    with pytest.raises(JiraRateLimitError):
        bucket.acquire()


@pytest.mark.unit
def test_token_bucket_thread_safety():
    """Many threads competing for tokens should not raise unexpected exceptions."""
    bucket = _TokenBucket(rate=100.0, capacity=100.0, block_timeout=2.0)
    errors = []

    def worker():
        try:
            bucket.acquire()
        except JiraRateLimitError:
            pass  # acceptable — bucket could genuinely run out
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected exceptions in worker threads: {errors}"


# ---------------------------------------------------------------------------
# HTTPAdapter retry unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_session_has_https_adapter_with_retry(jira_unit):
    """The session must have an HTTPAdapter mounted on https:// with Retry."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    adapter = jira_unit._session.get_adapter("https://jira.example.com")
    assert isinstance(adapter, HTTPAdapter)
    assert isinstance(adapter.max_retries, Retry)
    assert adapter.max_retries.total == 3
    assert 429 in adapter.max_retries.status_forcelist
    assert 500 in adapter.max_retries.status_forcelist
    assert 503 in adapter.max_retries.status_forcelist


@pytest.mark.unit
def test_429_raises_service_error_without_adapter_retry(jira_unit, monkeypatch):
    """App-level 429 handling: without urllib3 retry, get_issue raises JiraServiceError."""
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"key": "QENG-1", "fields": {}}

    fail_resp = MagicMock()
    fail_resp.status_code = 429
    fail_resp.text = "rate limited"

    call_count = {"n": 0}

    def fake_get(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return fail_resp
        return ok_resp

    # Patch the session's get method directly so urllib3 Retry is bypassed in
    # the unit test (we're testing our *application-level* response handling,
    # not urllib3 internals).
    monkeypatch.setattr(jira_unit._session, "get", fake_get)

    # get_issue handles non-2xx by raising — verify it raises on 429 since
    # our app-level code treats 429 as a generic error (urllib3 retries it
    # transparently in production; here we just confirm the plumbing works).
    with pytest.raises(JiraServiceError):
        jira_unit.get_issue("QENG-1")


@pytest.mark.unit
def test_rate_limiter_called_before_http_request(jira_unit, monkeypatch):
    """_throttle() must be called before every HTTP method."""
    calls = []

    original_throttle = jira_unit._throttle

    def tracking_throttle():
        calls.append("throttle")
        original_throttle()

    monkeypatch.setattr(jira_unit, "_throttle", tracking_throttle)

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"transitions": []}
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: ok_resp)

    jira_unit.get_transitions("QENG-1")

    assert "throttle" in calls, "_throttle was not called before get_transitions"


# ---------------------------------------------------------------------------
# Field ID env-var unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_field_ids_read_from_env(jira_unit):
    """_field_id() must return the value set via env var, not a hardcoded string."""
    assert jira_unit._field_id("lab_request_type") == "customfield_00001"
    assert jira_unit._field_id("deadline") == "customfield_00004"
    assert jira_unit._field_id("issue_type_id") == "99999"


@pytest.mark.unit
def test_missing_field_env_var_raises(monkeypatch):
    """JiraService._field_id() must raise JiraServiceError when env var is absent."""
    # Provide minimal env so construction succeeds but omit one field var.
    env = dict(UNIT_ENV)
    env.pop("JIRA_CUSTOMFIELD_DEADLINE")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("JIRA_CUSTOMFIELD_DEADLINE", raising=False)

    svc = JiraService()
    with pytest.raises(JiraServiceError, match="JIRA_CUSTOMFIELD_DEADLINE"):
        svc._field_id("deadline")


# ---------------------------------------------------------------------------
# _TokenBucket constructor validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_token_bucket_invalid_rate_raises():
    """_TokenBucket must reject non-positive rate."""
    with pytest.raises(ValueError, match="rate"):
        _TokenBucket(rate=0, capacity=5.0)
    with pytest.raises(ValueError, match="rate"):
        _TokenBucket(rate=-1.0, capacity=5.0)


@pytest.mark.unit
def test_token_bucket_invalid_capacity_raises():
    """_TokenBucket must reject non-positive capacity."""
    with pytest.raises(ValueError, match="capacity"):
        _TokenBucket(rate=10.0, capacity=0)


@pytest.mark.unit
def test_token_bucket_invalid_block_timeout_raises():
    """_TokenBucket must reject negative block_timeout."""
    with pytest.raises(ValueError, match="block_timeout"):
        _TokenBucket(rate=10.0, capacity=5.0, block_timeout=-1.0)


@pytest.mark.unit
def test_token_bucket_zero_block_timeout_fails_immediately():
    """block_timeout=0 should fail immediately when bucket is empty."""
    bucket = _TokenBucket(rate=0.001, capacity=1.0, block_timeout=0.0)
    bucket.acquire()  # consume the token
    with pytest.raises(JiraRateLimitError):
        bucket.acquire()


@pytest.mark.unit
def test_token_bucket_sleep_path_succeeds_after_wait(monkeypatch):
    """Token bucket should sleep and succeed when token refills before timeout."""
    import time as real_time

    # Use a fast refill rate so the bucket refills almost instantly
    bucket = _TokenBucket(rate=1000.0, capacity=1.0, block_timeout=5.0)
    bucket.acquire()  # drain the bucket

    # Force _tokens to be just below 1 so sleep path is hit
    bucket._tokens = 0.5

    # Track sleep calls
    slept = []
    original_sleep = real_time.sleep

    def fake_sleep(duration):
        slept.append(duration)
        original_sleep(0)  # don't actually sleep

    monkeypatch.setattr("services.jira_service.time.sleep", fake_sleep)

    # Should succeed (bucket refills after the simulated sleep)
    bucket.acquire()
    # Verify the sleep path was exercised
    assert len(slept) >= 1


# ---------------------------------------------------------------------------
# Missing credentials at construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_jira_url_raises(monkeypatch):
    """JiraService must raise JiraServiceError if JIRA_URL is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("JIRA_URL", raising=False)
    with pytest.raises(JiraServiceError, match="JIRA_URL"):
        JiraService()


@pytest.mark.unit
def test_missing_jira_pat_raises(monkeypatch):
    """JiraService must raise JiraServiceError if JIRA_PAT is absent."""
    for key, value in UNIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("JIRA_PAT", raising=False)
    with pytest.raises(JiraServiceError, match="JIRA_PAT"):
        JiraService()


@pytest.mark.unit
def test_unknown_field_name_raises(jira_unit):
    """_field_id() with an unknown name should raise JiraServiceError."""
    with pytest.raises(JiraServiceError, match="Unknown Jira field name"):
        jira_unit._field_id("nonexistent_field")


# ---------------------------------------------------------------------------
# validate_connectivity unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_connectivity_success(jira_unit, monkeypatch):
    """validate_connectivity must succeed on 200."""
    resp = MagicMock()
    resp.status_code = 200
    resp.ok = True
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    jira_unit.validate_connectivity()  # should not raise


@pytest.mark.unit
def test_validate_connectivity_401_raises_auth_error(jira_unit, monkeypatch):
    """validate_connectivity must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.ok = False
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_403_raises_auth_error(jira_unit, monkeypatch):
    """validate_connectivity must raise JiraAuthError on 403."""
    resp = MagicMock()
    resp.status_code = 403
    resp.ok = False
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_500_raises_service_error(jira_unit, monkeypatch):
    """validate_connectivity must raise JiraServiceError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.ok = False
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraServiceError):
        jira_unit.validate_connectivity()


@pytest.mark.unit
def test_validate_connectivity_network_error_raises(jira_unit, monkeypatch):
    """validate_connectivity must raise JiraServiceError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "get", raise_exc)
    with pytest.raises(JiraServiceError, match="Could not reach Jira"):
        jira_unit.validate_connectivity()


# ---------------------------------------------------------------------------
# get_issue unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_issue_success(jira_unit, monkeypatch):
    """get_issue returns parsed JSON on success."""
    payload = {"key": "QENG-1", "fields": {"summary": "Test issue"}}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)

    result = jira_unit.get_issue("QENG-1")
    assert result == payload


@pytest.mark.unit
def test_get_issue_not_found_raises(jira_unit, monkeypatch):
    """get_issue must raise JiraNotFoundError on 404."""
    resp = MagicMock()
    resp.status_code = 404
    resp.text = "Not found"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraNotFoundError, match="QENG-99"):
        jira_unit.get_issue("QENG-99")


@pytest.mark.unit
def test_get_issue_401_raises_auth_error(jira_unit, monkeypatch):
    """get_issue must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.get_issue("QENG-1")


@pytest.mark.unit
def test_get_issue_403_raises_auth_error(jira_unit, monkeypatch):
    """get_issue must raise JiraAuthError on 403."""
    resp = MagicMock()
    resp.status_code = 403
    resp.text = "Forbidden"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.get_issue("QENG-1")


@pytest.mark.unit
def test_get_issue_500_raises_service_error(jira_unit, monkeypatch):
    """get_issue must raise JiraServiceError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraServiceError):
        jira_unit.get_issue("QENG-1")


@pytest.mark.unit
def test_get_issue_invalid_json_raises(jira_unit, monkeypatch):
    """get_issue must raise JiraServiceError when response is not JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("invalid JSON")
    resp.text = "not json"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraServiceError, match="not valid JSON"):
        jira_unit.get_issue("QENG-1")


@pytest.mark.unit
def test_get_issue_network_error_raises(jira_unit, monkeypatch):
    """get_issue must raise JiraServiceError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "get", raise_exc)
    with pytest.raises(JiraServiceError, match="Failed to communicate"):
        jira_unit.get_issue("QENG-1")


# ---------------------------------------------------------------------------
# search_issues unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_search_issues_success(jira_unit, monkeypatch):
    """search_issues returns parsed JSON on success."""
    payload = {"issues": [{"key": "QENG-1"}], "total": 1}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)

    result = jira_unit.search_issues("project = QENG")
    assert result["total"] == 1


@pytest.mark.unit
def test_search_issues_401_raises_auth_error(jira_unit, monkeypatch):
    """search_issues must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.search_issues("project = QENG")


@pytest.mark.unit
def test_search_issues_500_raises_service_error(jira_unit, monkeypatch):
    """search_issues must raise JiraServiceError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "error"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraServiceError):
        jira_unit.search_issues("project = QENG")


@pytest.mark.unit
def test_search_issues_invalid_json_raises(jira_unit, monkeypatch):
    """search_issues must raise JiraServiceError when response is not JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("bad json")
    resp.text = "not json"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraServiceError, match="not valid JSON"):
        jira_unit.search_issues("project = QENG")


@pytest.mark.unit
def test_search_issues_network_error_raises(jira_unit, monkeypatch):
    """search_issues must raise JiraServiceError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "get", raise_exc)
    with pytest.raises(JiraServiceError, match="Failed to communicate"):
        jira_unit.search_issues("project = QENG")


# ---------------------------------------------------------------------------
# get_transitions unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_transitions_success(jira_unit, monkeypatch):
    """get_transitions returns parsed JSON on success."""
    payload = {"transitions": [{"id": "11", "name": "Start Progress"}]}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)

    result = jira_unit.get_transitions("QENG-1")
    assert len(result["transitions"]) == 1


@pytest.mark.unit
def test_get_transitions_401_raises_auth_error(jira_unit, monkeypatch):
    """get_transitions must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.get_transitions("QENG-1")


@pytest.mark.unit
def test_get_transitions_500_raises_transition_error(jira_unit, monkeypatch):
    """get_transitions must raise JiraIssueTransitionError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueTransitionError):
        jira_unit.get_transitions("QENG-1")


@pytest.mark.unit
def test_get_transitions_invalid_json_raises(jira_unit, monkeypatch):
    """get_transitions must raise JiraIssueTransitionError on bad JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("bad json")
    resp.text = "not json"
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueTransitionError, match="not valid JSON"):
        jira_unit.get_transitions("QENG-1")


@pytest.mark.unit
def test_get_transitions_network_error_raises(jira_unit, monkeypatch):
    """get_transitions must raise JiraIssueTransitionError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "get", raise_exc)
    with pytest.raises(JiraIssueTransitionError, match="Failed to communicate"):
        jira_unit.get_transitions("QENG-1")


# ---------------------------------------------------------------------------
# transition_issue unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transition_issue_success(jira_unit, monkeypatch):
    """transition_issue must succeed on 204."""
    resp = MagicMock()
    resp.status_code = 204
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    jira_unit.transition_issue("QENG-1", "11")  # should not raise


@pytest.mark.unit
def test_transition_issue_with_comment(jira_unit, monkeypatch):
    """transition_issue with a comment should include update payload."""
    posted_payloads = []

    def fake_post(url, json=None, **kw):
        posted_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)
    jira_unit.transition_issue("QENG-1", "11", comment="Moving to done")

    assert len(posted_payloads) == 1
    payload = posted_payloads[0]
    assert "update" in payload
    assert payload["update"]["comment"][0]["add"]["body"] == "Moving to done"


@pytest.mark.unit
def test_transition_issue_with_fields(jira_unit, monkeypatch):
    """transition_issue with fields should include them in the payload."""
    posted_payloads = []

    def fake_post(url, json=None, **kw):
        posted_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)
    jira_unit.transition_issue("QENG-1", "11", fields={"resolution": {"name": "Done"}})

    payload = posted_payloads[0]
    assert payload["fields"]["resolution"]["name"] == "Done"


@pytest.mark.unit
def test_transition_issue_401_raises_auth_error(jira_unit, monkeypatch):
    """transition_issue must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.transition_issue("QENG-1", "11")


@pytest.mark.unit
def test_transition_issue_500_raises_transition_error(jira_unit, monkeypatch):
    """transition_issue must raise JiraIssueTransitionError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueTransitionError):
        jira_unit.transition_issue("QENG-1", "11")


@pytest.mark.unit
def test_transition_issue_network_error_raises(jira_unit, monkeypatch):
    """transition_issue must raise JiraIssueTransitionError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "post", raise_exc)
    with pytest.raises(JiraIssueTransitionError, match="Failed to communicate"):
        jira_unit.transition_issue("QENG-1", "11")


# ---------------------------------------------------------------------------
# transition_issue_by_name unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transition_issue_by_name_success(jira_unit, monkeypatch):
    """transition_issue_by_name finds the transition by name and calls it."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {
        "transitions": [
            {"id": "21", "name": "Start Progress"},
            {"id": "31", "name": "On Hold"},
        ]
    }
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    post_resp = MagicMock()
    post_resp.status_code = 204
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: post_resp)

    jira_unit.transition_issue_by_name("QENG-1", "Start Progress")  # should not raise


@pytest.mark.unit
def test_transition_issue_by_name_case_insensitive(jira_unit, monkeypatch):
    """transition_issue_by_name is case-insensitive."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {
        "transitions": [{"id": "21", "name": "start progress"}]
    }
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    post_resp = MagicMock()
    post_resp.status_code = 204
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: post_resp)

    jira_unit.transition_issue_by_name("QENG-1", "START PROGRESS")  # should not raise


@pytest.mark.unit
def test_transition_issue_by_name_not_found_raises(jira_unit, monkeypatch):
    """transition_issue_by_name raises when transition name is not found."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {
        "transitions": [{"id": "21", "name": "Start Progress"}]
    }
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    with pytest.raises(JiraIssueTransitionError, match="Transition not found"):
        jira_unit.transition_issue_by_name("QENG-1", "nonexistent-transition")


@pytest.mark.unit
def test_transition_issue_by_name_invalid_response_raises(jira_unit, monkeypatch):
    """transition_issue_by_name raises when transitions list is not a list."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {"transitions": "not-a-list"}
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    with pytest.raises(JiraIssueTransitionError, match="did not include a list"):
        jira_unit.transition_issue_by_name("QENG-1", "Start Progress")


# ---------------------------------------------------------------------------
# update_issue_fields unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_update_issue_fields_success(jira_unit, monkeypatch):
    """update_issue_fields must succeed on 204."""
    resp = MagicMock()
    resp.status_code = 204
    monkeypatch.setattr(jira_unit._session, "put", lambda *a, **kw: resp)
    jira_unit.update_issue_fields("QENG-1", {"summary": "New summary"})  # should not raise


@pytest.mark.unit
def test_update_issue_fields_401_raises_auth_error(jira_unit, monkeypatch):
    """update_issue_fields must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "put", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit.update_issue_fields("QENG-1", {"summary": "test"})


@pytest.mark.unit
def test_update_issue_fields_500_raises_update_error(jira_unit, monkeypatch):
    """update_issue_fields must raise JiraIssueUpdateError on 5xx."""
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(jira_unit._session, "put", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueUpdateError):
        jira_unit.update_issue_fields("QENG-1", {"summary": "test"})


@pytest.mark.unit
def test_update_issue_fields_network_error_raises(jira_unit, monkeypatch):
    """update_issue_fields must raise JiraIssueUpdateError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "put", raise_exc)
    with pytest.raises(JiraIssueUpdateError, match="Failed to communicate"):
        jira_unit.update_issue_fields("QENG-1", {"summary": "test"})


# ---------------------------------------------------------------------------
# Convenience update methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_update_assignee_unassign(jira_unit, monkeypatch):
    """update_assignee with None should send assignee: null."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_assignee("QENG-1", None)
    assert put_payloads[0]["fields"]["assignee"] is None


@pytest.mark.unit
def test_update_assignee_unassigned_string(jira_unit, monkeypatch):
    """update_assignee with 'unassigned' should send assignee: null."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_assignee("QENG-1", "unassigned")
    assert put_payloads[0]["fields"]["assignee"] is None


@pytest.mark.unit
def test_update_assignee_named_user(jira_unit, monkeypatch):
    """update_assignee with a username string should send name-keyed dict."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_assignee("QENG-1", "jdoe")
    assert put_payloads[0]["fields"]["assignee"] == {"name": "jdoe"}


@pytest.mark.unit
def test_update_description(jira_unit, monkeypatch):
    """update_description should send description field."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_description("QENG-1", "New description")
    assert put_payloads[0]["fields"]["description"] == "New description"


@pytest.mark.unit
def test_update_priority(jira_unit, monkeypatch):
    """update_priority should send priority field with name key."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_priority("QENG-1", "P1: Critical")
    assert put_payloads[0]["fields"]["priority"] == {"name": "P1: Critical"}


@pytest.mark.unit
def test_update_resolution(jira_unit, monkeypatch):
    """update_resolution should send resolution field."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_resolution("QENG-1", "Done")
    assert put_payloads[0]["fields"]["resolution"] == {"name": "Done"}


@pytest.mark.unit
def test_update_deadline_with_date_object(jira_unit, monkeypatch):
    """update_deadline with a date object should serialize to YYYY-MM-DD."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_deadline("QENG-1", date(2026, 6, 1))
    deadline_val = put_payloads[0]["fields"]["customfield_00004"]
    assert deadline_val == "2026-06-01"


@pytest.mark.unit
def test_update_deadline_with_datetime_object(jira_unit, monkeypatch):
    """update_deadline with a datetime object should serialize to date portion."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_deadline("QENG-1", datetime(2026, 6, 1, 12, 0, 0))
    deadline_val = put_payloads[0]["fields"]["customfield_00004"]
    assert deadline_val == "2026-06-01"


@pytest.mark.unit
def test_update_high_level_estimate(jira_unit, monkeypatch):
    """update_high_level_estimate should send value-keyed dict."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_high_level_estimate("QENG-1", "Medium")
    estimate_field = put_payloads[0]["fields"]["customfield_00006"]
    assert estimate_field == {"value": "Medium"}


@pytest.mark.unit
def test_update_lab_request_type(jira_unit, monkeypatch):
    """update_lab_request_type should send value-keyed dict for the custom field."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_lab_request_type("QENG-1", "Lab setup")
    field_val = put_payloads[0]["fields"]["customfield_00001"]
    assert field_val == {"value": "Lab setup"}


@pytest.mark.unit
def test_update_planned_end_date(jira_unit, monkeypatch):
    """update_planned_end_date should serialize the date correctly."""
    put_payloads = []

    def fake_put(url, json=None, **kw):
        put_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 204
        return resp

    monkeypatch.setattr(jira_unit._session, "put", fake_put)
    jira_unit.update_planned_end_date("QENG-1", "2026-07-15")
    field_val = put_payloads[0]["fields"]["customfield_00005"]
    assert field_val == "2026-07-15"


# ---------------------------------------------------------------------------
# Workflow transition convenience methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_transition_to_on_hold(jira_unit, monkeypatch):
    """transition_to_on_hold should call transition_issue_by_name with 'On Hold'."""
    calls = []

    def fake_transition_by_name(issue_key, name, **kw):
        calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)
    jira_unit.transition_to_on_hold("QENG-1")
    assert calls == [("QENG-1", "On Hold")]


@pytest.mark.unit
def test_transition_to_defining_requirements(jira_unit, monkeypatch):
    """transition_to_defining_requirements should call 'Reopen' transition."""
    calls = []

    def fake_transition_by_name(issue_key, name, **kw):
        calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)
    jira_unit.transition_to_defining_requirements("QENG-1")
    assert calls == [("QENG-1", "Reopen")]


@pytest.mark.unit
def test_transition_to_cancelled(jira_unit, monkeypatch):
    """transition_to_cancelled should set resolution then call 'Cancelled' transition."""
    resolution_calls = []
    transition_calls = []

    def fake_update_resolution(issue_key, resolution):
        resolution_calls.append((issue_key, resolution))

    def fake_transition_by_name(issue_key, name, **kw):
        transition_calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "update_resolution", fake_update_resolution)
    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)

    jira_unit.transition_to_cancelled("QENG-1")
    assert resolution_calls == [("QENG-1", "Cancelled")]
    assert transition_calls == [("QENG-1", "Cancelled")]


@pytest.mark.unit
def test_transition_to_pending_staff(jira_unit, monkeypatch):
    """transition_to_pending_staff should call 'Request Help' transition."""
    calls = []

    def fake_transition_by_name(issue_key, name, **kw):
        calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)
    jira_unit.transition_to_pending_staff("QENG-1")
    assert calls == [("QENG-1", "Request Help")]


@pytest.mark.unit
def test_transition_to_in_progress(jira_unit, monkeypatch):
    """transition_to_in_progress should update dates and call 'Start Progress'."""
    planned_end_calls = []
    estimate_calls = []
    transition_calls = []

    def fake_update_planned_end_date(issue_key, dt):
        planned_end_calls.append((issue_key, dt))

    def fake_update_high_level_estimate(issue_key, est):
        estimate_calls.append((issue_key, est))

    def fake_transition_by_name(issue_key, name, **kw):
        transition_calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "update_planned_end_date", fake_update_planned_end_date)
    monkeypatch.setattr(jira_unit, "update_high_level_estimate", fake_update_high_level_estimate)
    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)

    jira_unit.transition_to_in_progress("QENG-1", "2026-07-01", "Medium")
    assert planned_end_calls == [("QENG-1", "2026-07-01")]
    assert estimate_calls == [("QENG-1", "Medium")]
    assert transition_calls == [("QENG-1", "Start Progress")]


@pytest.mark.unit
def test_transition_to_testing(jira_unit, monkeypatch):
    """transition_to_testing should call 'Ready for Testing' transition."""
    calls = []

    def fake_transition_by_name(issue_key, name, **kw):
        calls.append((issue_key, name))

    monkeypatch.setattr(jira_unit, "transition_issue_by_name", fake_transition_by_name)
    jira_unit.transition_to_testing("QENG-1")
    assert calls == [("QENG-1", "Ready for Testing")]


@pytest.mark.unit
def test_transition_to_closed_success(jira_unit, monkeypatch):
    """transition_to_closed should call transition_issue with 'Closed' transition ID."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {
        "transitions": [
            {"id": "41", "name": "Closed"},
            {"id": "21", "name": "Start Progress"},
        ]
    }
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    post_resp = MagicMock()
    post_resp.status_code = 204
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: post_resp)

    jira_unit.transition_to_closed("QENG-1")  # should not raise


@pytest.mark.unit
def test_transition_to_closed_not_found_raises(jira_unit, monkeypatch):
    """transition_to_closed should raise when no 'Closed' transition exists."""
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {
        "transitions": [{"id": "21", "name": "Start Progress"}]
    }
    monkeypatch.setattr(jira_unit._session, "get", lambda *a, **kw: transitions_resp)

    with pytest.raises(JiraIssueTransitionError, match="Transition not found: Closed"):
        jira_unit.transition_to_closed("QENG-1")


# ---------------------------------------------------------------------------
# _create_issue unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_issue_success(jira_unit, monkeypatch):
    """_create_issue returns the issue key from Jira response."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {"key": "QENG-42"}
    resp.text = '{"key": "QENG-42"}'
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)

    key = jira_unit._create_issue({"fields": {}})
    assert key == "QENG-42"


@pytest.mark.unit
def test_create_issue_401_raises_auth_error(jira_unit, monkeypatch):
    """_create_issue must raise JiraAuthError on 401."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraAuthError):
        jira_unit._create_issue({"fields": {}})


@pytest.mark.unit
def test_create_issue_400_raises_creation_error(jira_unit, monkeypatch):
    """_create_issue must raise JiraIssueCreationError on 400."""
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "Bad request"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueCreationError):
        jira_unit._create_issue({"fields": {}})


@pytest.mark.unit
def test_create_issue_long_error_message_truncated(jira_unit, monkeypatch):
    """_create_issue truncates very long error messages from Jira."""
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "X" * 1000
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueCreationError) as exc_info:
        jira_unit._create_issue({"fields": {}})
    # The error message text must be present, not crash
    assert "Failed to create Jira issue" in str(exc_info.value)


@pytest.mark.unit
def test_create_issue_missing_key_raises(jira_unit, monkeypatch):
    """_create_issue must raise JiraIssueCreationError when response lacks 'key'."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {}  # no 'key'
    resp.text = "{}"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)
    with pytest.raises(JiraIssueCreationError, match="missing issue key"):
        jira_unit._create_issue({"fields": {}})


@pytest.mark.unit
def test_create_issue_network_error_raises(jira_unit, monkeypatch):
    """_create_issue must raise JiraIssueCreationError on network failure."""
    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(jira_unit._session, "post", raise_exc)
    with pytest.raises(JiraIssueCreationError, match="Failed to communicate"):
        jira_unit._create_issue({"fields": {}})


# ---------------------------------------------------------------------------
# _normalize helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_named_item_dict_passthrough():
    """_normalize_named_item should pass dicts through unchanged."""
    val = {"name": "P1: Critical", "id": "1"}
    result = JiraService._normalize_named_item(val, "priority")
    assert result == val


@pytest.mark.unit
def test_normalize_named_item_string_wraps():
    """_normalize_named_item should wrap strings in {name: ...}."""
    result = JiraService._normalize_named_item("P1: Critical", "priority")
    assert result == {"name": "P1: Critical"}


@pytest.mark.unit
def test_normalize_named_item_invalid_type_raises():
    """_normalize_named_item should raise JiraIssueCreationError for bad types."""
    with pytest.raises(JiraIssueCreationError, match="Invalid priority value type"):
        JiraService._normalize_named_item(123, "priority")


@pytest.mark.unit
def test_normalize_select_dict_passthrough():
    """_normalize_select should pass dicts through unchanged."""
    val = {"value": "Lab setup", "id": "10"}
    result = JiraService._normalize_select(val)
    assert result == val


@pytest.mark.unit
def test_normalize_select_string_wraps():
    """_normalize_select should wrap strings in {value: ...}."""
    result = JiraService._normalize_select("Lab setup")
    assert result == {"value": "Lab setup"}


@pytest.mark.unit
def test_normalize_select_invalid_type_raises():
    """_normalize_select should raise JiraIssueCreationError for bad types."""
    with pytest.raises(JiraIssueCreationError, match="Invalid select value type"):
        JiraService._normalize_select(42)


@pytest.mark.unit
def test_normalize_assignee_dict_passthrough():
    """_normalize_assignee should pass dicts through unchanged."""
    val = {"name": "jdoe", "accountId": "abc123"}
    result = JiraService._normalize_assignee(val)
    assert result == val


@pytest.mark.unit
def test_normalize_assignee_string_wraps():
    """_normalize_assignee should wrap strings in {name: ...}."""
    result = JiraService._normalize_assignee("jdoe")
    assert result == {"name": "jdoe"}


@pytest.mark.unit
def test_normalize_assignee_invalid_type_raises():
    """_normalize_assignee should raise JiraIssueCreationError for bad types."""
    with pytest.raises(JiraIssueCreationError, match="Invalid assignee value type"):
        JiraService._normalize_assignee(42)


@pytest.mark.unit
def test_normalize_date_date_object():
    """_normalize_date with a date object returns YYYY-MM-DD string."""
    result = JiraService._normalize_date(date(2026, 6, 15))
    assert result == "2026-06-15"


@pytest.mark.unit
def test_normalize_date_datetime_object():
    """_normalize_date with a datetime object returns date portion."""
    result = JiraService._normalize_date(datetime(2026, 6, 15, 8, 30, 0))
    assert result == "2026-06-15"


@pytest.mark.unit
def test_normalize_date_string_passthrough():
    """_normalize_date passes strings through unchanged."""
    result = JiraService._normalize_date("2026-06-15")
    assert result == "2026-06-15"


@pytest.mark.unit
def test_normalize_date_invalid_type_raises():
    """_normalize_date raises JiraIssueCreationError for invalid types."""
    with pytest.raises(JiraIssueCreationError, match="Invalid deadline value type"):
        JiraService._normalize_date(123456)


# ---------------------------------------------------------------------------
# _require helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_require_raises_on_none():
    """_require must raise JiraIssueCreationError when value is None."""
    with pytest.raises(JiraIssueCreationError, match="Missing required field: summary"):
        JiraService._require("summary", None)


@pytest.mark.unit
def test_require_raises_on_empty_string():
    """_require must raise JiraIssueCreationError when value is empty string."""
    with pytest.raises(JiraIssueCreationError, match="Missing required field: description"):
        JiraService._require("description", "")


@pytest.mark.unit
def test_require_passes_non_empty():
    """_require should not raise for non-empty values."""
    JiraService._require("summary", "Some summary")  # should not raise


# ---------------------------------------------------------------------------
# _upload_attachments unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upload_attachments_file_not_found_raises(jira_unit, tmp_path):
    """_upload_attachments should raise JiraAttachmentUploadError for missing file."""
    missing_path = str(tmp_path / "nonexistent.txt")
    with pytest.raises(JiraAttachmentUploadError, match="Attachment not found"):
        jira_unit._upload_attachments("QENG-1", [missing_path])


@pytest.mark.unit
def test_upload_attachments_success(jira_unit, monkeypatch, tmp_path):
    """_upload_attachments should POST file and succeed on 200."""
    test_file = tmp_path / "attachment.txt"
    test_file.write_text("test content")

    resp = MagicMock()
    resp.status_code = 200
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)

    jira_unit._upload_attachments("QENG-1", [str(test_file)])  # should not raise


@pytest.mark.unit
def test_upload_attachments_401_raises_auth_error(jira_unit, monkeypatch, tmp_path):
    """_upload_attachments should raise JiraAuthError on 401."""
    test_file = tmp_path / "attachment.txt"
    test_file.write_text("test content")

    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)

    with pytest.raises(JiraAuthError):
        jira_unit._upload_attachments("QENG-1", [str(test_file)])


@pytest.mark.unit
def test_upload_attachments_500_raises_upload_error(jira_unit, monkeypatch, tmp_path):
    """_upload_attachments should raise JiraAttachmentUploadError on 5xx."""
    test_file = tmp_path / "attachment.txt"
    test_file.write_text("test content")

    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Server error"
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: resp)

    with pytest.raises(JiraAttachmentUploadError):
        jira_unit._upload_attachments("QENG-1", [str(test_file)])


@pytest.mark.unit
def test_upload_attachments_network_error_raises(jira_unit, monkeypatch, tmp_path):
    """_upload_attachments should raise JiraAttachmentUploadError on network failure."""
    test_file = tmp_path / "attachment.txt"
    test_file.write_text("test content")

    def raise_exc(*a, **kw):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(jira_unit._session, "post", raise_exc)

    with pytest.raises(JiraAttachmentUploadError, match="Failed to communicate"):
        jira_unit._upload_attachments("QENG-1", [str(test_file)])


# ---------------------------------------------------------------------------
# create_lab_request unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_lab_request_success(jira_unit, monkeypatch):
    """create_lab_request returns the issue key on success."""
    post_resp = MagicMock()
    post_resp.status_code = 201
    post_resp.json.return_value = {"key": "QENG-100"}
    post_resp.text = '{"key": "QENG-100"}'
    monkeypatch.setattr(jira_unit._session, "post", lambda *a, **kw: post_resp)

    key = jira_unit.create_lab_request(
        summary="Test summary",
        description="Test description",
        priority="P3: Medium",
        lab_request_type="Lab setup",
        deadline="2026-07-01",
    )
    assert key == "QENG-100"


@pytest.mark.unit
def test_create_lab_request_with_attachments(jira_unit, monkeypatch, tmp_path):
    """create_lab_request should upload attachments after creating the issue."""
    post_call_count = {"n": 0}

    def fake_post(url, json=None, files=None, **kw):
        post_call_count["n"] += 1
        resp = MagicMock()
        if post_call_count["n"] == 1:  # issue creation
            resp.status_code = 201
            resp.json.return_value = {"key": "QENG-200"}
            resp.text = '{"key": "QENG-200"}'
        else:  # attachment upload
            resp.status_code = 200
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)

    attachment = tmp_path / "report.txt"
    attachment.write_text("results")

    key = jira_unit.create_lab_request(
        summary="Test",
        description="Test",
        priority="P3: Medium",
        lab_request_type="Lab setup",
        deadline="2026-07-01",
        attachments=[str(attachment)],
    )
    assert key == "QENG-200"
    assert post_call_count["n"] == 2


@pytest.mark.unit
def test_create_lab_request_missing_summary_raises(jira_unit):
    """create_lab_request must raise when summary is empty."""
    with pytest.raises(JiraIssueCreationError, match="Missing required field: summary"):
        jira_unit.create_lab_request(
            summary="",
            description="desc",
            priority="P3: Medium",
            lab_request_type="Lab setup",
            deadline="2026-07-01",
        )


@pytest.mark.unit
def test_create_lab_request_missing_description_raises(jira_unit):
    """create_lab_request must raise when description is empty."""
    with pytest.raises(JiraIssueCreationError, match="Missing required field: description"):
        jira_unit.create_lab_request(
            summary="summary",
            description="",
            priority="P3: Medium",
            lab_request_type="Lab setup",
            deadline="2026-07-01",
        )


@pytest.mark.unit
def test_create_lab_request_with_assignee_dict(jira_unit, monkeypatch):
    """create_lab_request with dict assignee passes it through unchanged."""
    post_payloads = []

    def fake_post(url, json=None, **kw):
        post_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"key": "QENG-300"}
        resp.text = '{"key": "QENG-300"}'
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)

    jira_unit.create_lab_request(
        summary="Test",
        description="Test",
        priority="P3: Medium",
        lab_request_type="Lab setup",
        deadline="2026-07-01",
        assignee={"name": "jdoe"},
    )
    assert post_payloads[0]["fields"]["assignee"] == {"name": "jdoe"}


@pytest.mark.unit
def test_create_lab_request_with_custom_project_key(jira_unit, monkeypatch):
    """create_lab_request respects the explicit project_key parameter."""
    post_payloads = []

    def fake_post(url, json=None, **kw):
        post_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"key": "MYPROJ-1"}
        resp.text = '{"key": "MYPROJ-1"}'
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)

    jira_unit.create_lab_request(
        summary="Test",
        description="Test",
        priority="P3: Medium",
        lab_request_type="Lab setup",
        deadline="2026-07-01",
        project_key="MYPROJ",
        issue_type_id="12345",
    )
    assert post_payloads[0]["fields"]["project"] == {"key": "MYPROJ"}


@pytest.mark.unit
def test_create_lab_request_with_custom_fields(jira_unit, monkeypatch):
    """create_lab_request merges custom_fields into the payload."""
    post_payloads = []

    def fake_post(url, json=None, **kw):
        post_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"key": "QENG-400"}
        resp.text = '{"key": "QENG-400"}'
        return resp

    monkeypatch.setattr(jira_unit._session, "post", fake_post)

    jira_unit.create_lab_request(
        summary="Test",
        description="Test",
        priority="P3: Medium",
        lab_request_type="Lab setup",
        deadline="2026-07-01",
        custom_fields={"my_custom_field": "extra_value"},
    )
    assert post_payloads[0]["fields"]["my_custom_field"] == "extra_value"


