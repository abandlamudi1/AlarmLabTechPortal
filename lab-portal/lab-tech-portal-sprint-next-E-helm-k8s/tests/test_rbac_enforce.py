"""Tests for RBAC enforce mode and audit-denial logging (Slice B, Issue #63).

Verifies that:
  - Non-admin hitting /systems/<id>/hard-delete returns 403 (a real tool endpoint)
  - The denial is written to the audit log DB
  - Lab-tech user hitting an admin-only endpoint returns 403
  - rbac.denial audit event contains required role and user tier
"""
from __future__ import annotations

import pytest
import services.audit_log as audit_log_module


@pytest.fixture(autouse=True)
def _isolated_audit_db(tmp_path, monkeypatch):
    """Redirect audit_log.DB_PATH to a temp file for every test."""
    db_path = str(tmp_path / "audit_enforce_test.db")
    monkeypatch.setattr(audit_log_module, "DB_PATH", db_path)
    audit_log_module.init_db()
    yield


def _make_mini_app(admin_groups: str = "Lab-Admins"):
    """Build a minimal Flask app with one admin-only route for isolation testing."""
    from flask import Flask
    from services.rbac import requires_role

    mini = Flask("rbac_enforce_test")
    mini.config["RBAC_ADMIN_GROUPS"] = admin_groups
    mini.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    mini.config["RBAC_LAB_TECH_GROUPS"] = "Lab-Techs"
    mini.config["LOGIN_DISABLED"] = False
    mini.config["SECRET_KEY"] = "test"

    @mini.route("/admin-only", methods=["POST"])
    @requires_role("admin")
    def admin_only():
        return "ok", 200

    @mini.route("/lab-tech-only", methods=["POST"])
    @requires_role("lab-tech")
    def lab_tech_only():
        return "ok", 200

    return mini


def test_viewer_hitting_admin_route_returns_403():
    """A viewer user must receive 403 on an admin-only endpoint."""
    mini = _make_mini_app()
    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "viewer@example.com",
                "groups": ["Everyone"],
            }
        response = c.post("/admin-only")
    assert response.status_code == 403


def test_lab_tech_hitting_admin_route_returns_403():
    """A lab-tech user must receive 403 on an admin-only endpoint."""
    mini = _make_mini_app()
    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "labtech@example.com",
                "groups": ["Lab-Techs"],
            }
        response = c.post("/admin-only")
    assert response.status_code == 403


def test_admin_hitting_admin_route_returns_200():
    """An admin user must pass through and receive 200."""
    mini = _make_mini_app()
    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "admin@example.com",
                "groups": ["Lab-Admins"],
            }
        response = c.post("/admin-only")
    assert response.status_code == 200


def test_lab_tech_hitting_lab_tech_route_returns_200():
    """A lab-tech user must pass through a lab-tech route (200)."""
    mini = _make_mini_app()
    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "labtech@example.com",
                "groups": ["Lab-Techs"],
            }
        response = c.post("/lab-tech-only")
    assert response.status_code == 200


def test_rbac_denial_writes_audit_event():
    """A 403 denial must write an rbac.denial event to the audit log."""
    mini = _make_mini_app()
    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "denied@example.com",
                "groups": ["Everyone"],
            }
        c.post("/admin-only")

    events = audit_log_module.get_recent_events(limit=10)
    denial_events = [ev for ev in events if ev["action"] == "rbac.denial"]
    assert len(denial_events) >= 1, "Expected at least one rbac.denial audit event"
    ev = denial_events[0]
    assert ev["actor"] == "denied@example.com"
    assert ev["detail"]["required"] == "admin"
    assert ev["detail"]["user_tier"] == "viewer"


def test_hard_delete_returns_403_for_viewer(app, client):
    """Non-admin user hitting /systems/<id>/hard-delete must get 403.

    This test targets the real system_locator route with LOGIN_DISABLED=False
    and an authenticated but under-privileged session.
    """
    app.config["LOGIN_DISABLED"] = False
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"

    with client.session_transaction() as sess:
        sess["user_identity"] = {
            "email": "viewer@example.com",
            "groups": ["Everyone"],
        }
        # flask-login requires _user_id in the session
        sess["_user_id"] = "viewer@example.com"

    response = client.post(
        "/systems/1/hard-delete",
        data={"pin": "0000"},
    )
    assert response.status_code == 403

    # Restore LOGIN_DISABLED so other tests are not affected
    app.config["LOGIN_DISABLED"] = True
