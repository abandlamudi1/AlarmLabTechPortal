"""Tests for the shared audit log service (Slice B, Issue #46).

Covers:
  - log_event() writes a record to the DB
  - get_recent_events() returns events newest-first
  - get_recent_events() pagination via limit/offset
  - detail dict is round-tripped as JSON
  - /api/v1/audit-log endpoint returns paginated JSON
"""
from __future__ import annotations

import pytest
import services.audit_log as audit_log_module


@pytest.fixture(autouse=True)
def _isolated_audit_db(tmp_path, monkeypatch):
    """Redirect audit_log.DB_PATH to a temp file for every test."""
    db_path = str(tmp_path / "audit_test.db")
    monkeypatch.setattr(audit_log_module, "DB_PATH", db_path)
    audit_log_module.init_db()
    yield


# ---------------------------------------------------------------------------
# Unit tests — service layer
# ---------------------------------------------------------------------------


def test_log_event_creates_record(app):
    """log_event() must write one row that is retrievable via get_recent_events."""
    with app.app_context():
        audit_log_module.log_event(
            actor="alice@example.com",
            action="checkout.checkout",
            resource_type="equipment",
            resource_id=1,
            detail={"item_name": "Oscilloscope"},
        )

    events = audit_log_module.get_recent_events(limit=10)
    assert len(events) == 1
    ev = events[0]
    assert ev["actor"] == "alice@example.com"
    assert ev["action"] == "checkout.checkout"
    assert ev["resource_type"] == "equipment"
    assert ev["resource_id"] == "1"
    assert ev["detail"]["item_name"] == "Oscilloscope"


def test_log_event_no_detail(app):
    """log_event() must succeed with detail=None and store null."""
    with app.app_context():
        audit_log_module.log_event(
            actor="bob@example.com",
            action="checkout.return",
            resource_type="equipment",
            resource_id=2,
        )

    events = audit_log_module.get_recent_events(limit=10)
    assert len(events) == 1
    assert events[0]["detail"] is None


def test_get_recent_events_newest_first(app):
    """get_recent_events() must return rows with the highest id first."""
    with app.app_context():
        for i in range(3):
            audit_log_module.log_event(
                actor="user@example.com",
                action=f"test.action_{i}",
                resource_type="item",
                resource_id=i,
            )

    events = audit_log_module.get_recent_events(limit=10)
    assert len(events) == 3
    ids = [ev["id"] for ev in events]
    assert ids == sorted(ids, reverse=True), "Events must be ordered newest-first"


def test_get_recent_events_pagination(app):
    """get_recent_events() limit and offset must restrict result set."""
    with app.app_context():
        for i in range(5):
            audit_log_module.log_event(
                actor="user@example.com",
                action="paginate.test",
                resource_type="item",
                resource_id=i,
            )

    page1 = audit_log_module.get_recent_events(limit=2, offset=0)
    page2 = audit_log_module.get_recent_events(limit=2, offset=2)
    page3 = audit_log_module.get_recent_events(limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1

    all_ids = [ev["id"] for ev in (page1 + page2 + page3)]
    assert len(all_ids) == len(set(all_ids)), "No duplicate rows across pages"


def test_log_event_detail_roundtrip(app):
    """Nested detail dict must survive JSON round-trip intact."""
    detail = {"required": "admin", "user_tier": "viewer", "nested": {"key": 42}}
    with app.app_context():
        audit_log_module.log_event(
            actor="charlie@example.com",
            action="rbac.denial",
            resource_type="endpoint",
            resource_id="/api/v1/audit-log",
            detail=detail,
        )

    events = audit_log_module.get_recent_events(limit=1)
    assert events[0]["detail"] == detail


# ---------------------------------------------------------------------------
# Integration tests — /api/v1/audit-log endpoint
# ---------------------------------------------------------------------------


def test_audit_log_endpoint_returns_json(app, client):
    """GET /api/v1/audit-log must return 200 with events + count keys."""
    with app.app_context():
        audit_log_module.log_event(
            actor="dave@example.com",
            action="inventory.quantity_adjustment",
            resource_type="inventory_item",
            resource_id=7,
            detail={"change": -1},
        )

    resp = client.get("/api/v1/audit-log")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "events" in data
    assert "count" in data
    assert data["count"] == len(data["events"])
    assert data["count"] >= 1


def test_audit_log_endpoint_limit_offset(app, client):
    """Pagination query params must be honoured by the endpoint."""
    with app.app_context():
        for i in range(5):
            audit_log_module.log_event(
                actor="eve@example.com",
                action="test.endpoint_pagination",
                resource_type="item",
                resource_id=i,
            )

    resp = client.get("/api/v1/audit-log?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2


def test_audit_log_endpoint_invalid_params(app, client):
    """Non-integer limit/offset must return 400."""
    resp = client.get("/api/v1/audit-log?limit=abc")
    assert resp.status_code == 400


def test_audit_log_endpoint_negative_limit_rejected(client):
    """Negative limit must return 400 — SQLite LIMIT -1 means no limit."""
    resp = client.get("/api/v1/audit-log?limit=-1")
    assert resp.status_code == 400


def test_audit_log_endpoint_zero_limit_rejected(client):
    """limit=0 must return 400 — returning zero rows is not useful."""
    resp = client.get("/api/v1/audit-log?limit=0")
    assert resp.status_code == 400


def test_audit_log_endpoint_negative_offset_rejected(client):
    """Negative offset must return 400."""
    resp = client.get("/api/v1/audit-log?offset=-1")
    assert resp.status_code == 400
