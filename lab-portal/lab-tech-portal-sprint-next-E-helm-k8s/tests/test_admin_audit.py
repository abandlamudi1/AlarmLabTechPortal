"""Tests for the admin audit-log dashboard and its supporting service layer.

Covers:
  - count_active_users() over a rolling window
  - get_activity_summary() counts + ordering
  - retention get/set round-trip and validation
  - purge_old_events() deletes only out-of-window rows
  - GET /admin/audit-log renders stats + events
  - POST /admin/audit-log/retention updates / disables retention
  - tasks.periodic.purge_audit_log honours the configured retention
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import services.audit_log as audit_log_module


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iso(days_ago: float) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _insert(actor: str, action: str, days_ago: float) -> None:
    """Insert an audit event with a controlled timestamp directly into the DB."""
    with sqlite3.connect(audit_log_module.DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_events
                (actor, action, resource_type, resource_id, detail, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor, action, "thing", "1", None, _iso(days_ago)),
        )


# ---------------------------------------------------------------------------
# count_active_users
# ---------------------------------------------------------------------------

def test_count_active_users_distinct_in_window(app):
    _insert("alice@x.com", "checkout.checkout", days_ago=1)
    _insert("bob@x.com", "inventory.add_item", days_ago=2)
    _insert("alice@x.com", "checkout.return", days_ago=5)  # alice again, still 1
    _insert("carol@x.com", "checkout.checkout", days_ago=40)  # outside window
    assert audit_log_module.count_active_users(days=30) == 2


def test_count_active_users_empty(app):
    assert audit_log_module.count_active_users(days=30) == 0


# ---------------------------------------------------------------------------
# get_activity_summary
# ---------------------------------------------------------------------------

def test_activity_summary_counts_and_order(app):
    for _ in range(3):
        _insert("alice@x.com", "checkout.checkout", days_ago=1)
    _insert("bob@x.com", "inventory.add_item", days_ago=1)
    _insert("eve@x.com", "checkout.checkout", days_ago=90)  # outside window, ignored

    summary = audit_log_module.get_activity_summary(days=30)
    assert summary[0] == {"action": "checkout.checkout", "count": 3}
    assert {"action": "inventory.add_item", "count": 1} in summary


def test_activity_summary_empty(app):
    assert audit_log_module.get_activity_summary(days=30) == []


# ---------------------------------------------------------------------------
# retention get/set
# ---------------------------------------------------------------------------

def test_retention_default_none(app):
    assert audit_log_module.get_retention_days() is None


def test_retention_set_and_get(app):
    audit_log_module.set_retention_days(90)
    assert audit_log_module.get_retention_days() == 90


def test_retention_zero_disables(app):
    audit_log_module.set_retention_days(90)
    audit_log_module.set_retention_days(0)
    assert audit_log_module.get_retention_days() is None


def test_retention_none_disables(app):
    audit_log_module.set_retention_days(30)
    audit_log_module.set_retention_days(None)
    assert audit_log_module.get_retention_days() is None


def test_retention_negative_raises(app):
    with pytest.raises(ValueError):
        audit_log_module.set_retention_days(-5)


# ---------------------------------------------------------------------------
# purge_old_events
# ---------------------------------------------------------------------------

def test_purge_deletes_old_keeps_recent(app):
    _insert("alice@x.com", "checkout.checkout", days_ago=1)
    _insert("bob@x.com", "checkout.checkout", days_ago=100)
    deleted = audit_log_module.purge_old_events(30)
    assert deleted == 1
    remaining = audit_log_module.get_recent_events(limit=10)
    assert len(remaining) == 1
    assert remaining[0]["actor"] == "alice@x.com"


def test_purge_disabled_returns_zero(app):
    _insert("bob@x.com", "checkout.checkout", days_ago=100)
    assert audit_log_module.purge_old_events(0) == 0
    assert len(audit_log_module.get_recent_events(limit=10)) == 1


# ---------------------------------------------------------------------------
# Admin dashboard page
# ---------------------------------------------------------------------------

def test_admin_dashboard_renders(app, client):
    with app.app_context():
        audit_log_module.log_event(
            actor="dave@x.com",
            action="inventory.quantity_adjustment",
            resource_type="inventory_item",
            resource_id=7,
            detail={"change": -1},
        )
    resp = client.get("/admin/audit-log")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Audit Log" in body
    assert "Active user" in body
    assert "inventory.quantity_adjustment" in body
    assert "dave@x.com" in body


def test_admin_dashboard_empty_state(app, client):
    resp = client.get("/admin/audit-log")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "No audit events recorded yet." in body


def test_admin_retention_update(app, client):
    resp = client.post("/admin/audit-log/retention", data={"retention_days": "45"})
    assert resp.status_code == 302
    assert audit_log_module.get_retention_days() == 45


def test_admin_retention_blank_disables(app, client):
    audit_log_module.set_retention_days(45)
    resp = client.post("/admin/audit-log/retention", data={"retention_days": ""})
    assert resp.status_code == 302
    assert audit_log_module.get_retention_days() is None


def test_admin_retention_invalid_rejected(app, client):
    audit_log_module.set_retention_days(30)
    resp = client.post("/admin/audit-log/retention", data={"retention_days": "abc"})
    assert resp.status_code == 302
    assert "status=error" in resp.headers["Location"]
    assert audit_log_module.get_retention_days() == 30  # unchanged


# ---------------------------------------------------------------------------
# purge_audit_log Celery task
# ---------------------------------------------------------------------------

def test_purge_task_purges_when_configured(app):
    _insert("alice@x.com", "checkout.checkout", days_ago=1)
    _insert("bob@x.com", "checkout.checkout", days_ago=100)
    audit_log_module.set_retention_days(30)

    from tasks.periodic import purge_audit_log

    with app.app_context():
        result = purge_audit_log.run()

    assert result["deleted"] == 1
    assert result["retention_days"] == 30


def test_purge_task_noop_when_disabled(app):
    _insert("bob@x.com", "checkout.checkout", days_ago=100)

    from tasks.periodic import purge_audit_log

    with app.app_context():
        result = purge_audit_log.run()

    assert result["deleted"] == 0
    assert len(audit_log_module.get_recent_events(limit=10)) == 1
