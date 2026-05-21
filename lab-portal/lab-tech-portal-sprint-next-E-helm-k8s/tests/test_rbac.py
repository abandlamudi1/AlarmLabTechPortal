"""Tests for RBAC tier mapping and enforce-mode enforcement (Slice A, Issue #44; Slice B, Issue #63)."""
from __future__ import annotations

import logging

import pytest

from services.rbac import TIERS, get_user_tier, requires_role


# ---------------------------------------------------------------------------
# Tier mapping tests
# ---------------------------------------------------------------------------


def test_get_user_tier_admin(app):
    """User in the configured admin group must map to 'admin'."""
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins,Portal-Admins"
    app.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    app.config["RBAC_LAB_TECH_GROUPS"] = ""
    with app.app_context():
        tier = get_user_tier(["Lab-Admins", "Everyone"])
    assert tier == "admin"


def test_get_user_tier_lab_tech(app):
    """User in lab-tech group but not admin group must map to 'lab-tech'."""
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    app.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    app.config["RBAC_LAB_TECH_GROUPS"] = "Lab-Techs"
    with app.app_context():
        tier = get_user_tier(["Lab-Techs", "Everyone"])
    assert tier == "lab-tech"


def test_get_user_tier_viewer_when_no_match(app):
    """User with no matching groups must fall back to 'viewer'."""
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    app.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    app.config["RBAC_LAB_TECH_GROUPS"] = ""
    with app.app_context():
        tier = get_user_tier(["Everyone"])
    assert tier == "viewer"


def test_get_user_tier_most_privileged_wins(app):
    """If user is in both admin and lab-tech groups, 'admin' must win."""
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    app.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    app.config["RBAC_LAB_TECH_GROUPS"] = "Lab-Techs"
    with app.app_context():
        tier = get_user_tier(["Lab-Admins", "Lab-Techs"])
    assert tier == "admin"


def test_get_user_tier_empty_groups(app):
    """User with empty group list must get 'viewer'."""
    app.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    app.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    app.config["RBAC_LAB_TECH_GROUPS"] = ""
    with app.app_context():
        tier = get_user_tier([])
    assert tier == "viewer"


# ---------------------------------------------------------------------------
# Enforce-mode enforcement: non-admin hits admin route → 403 + denial logged
# ---------------------------------------------------------------------------


def test_requires_role_enforce_returns_403_for_non_admin(app, capsys):
    """In enforce mode (now default), requires_role('admin') returns 403 for a
    non-admin user and logs 'rbac_denial'.

    Uses capsys because services/rbac.py logs via structlog PrintLoggerFactory
    → stdout.
    """
    from flask import Flask

    mini = Flask("rbac_test")
    mini.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    mini.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    mini.config["RBAC_LAB_TECH_GROUPS"] = ""
    mini.config["LOGIN_DISABLED"] = False  # RBAC must run
    mini.config["SECRET_KEY"] = "test"

    @mini.route("/admin-action", methods=["POST"])
    @requires_role("admin")
    def admin_action():
        return "ok", 200

    with mini.test_client() as c:
        with c.session_transaction() as sess:
            # Non-admin user — groups don't include Lab-Admins
            sess["user_identity"] = {
                "email": "viewer@example.com",
                "groups": ["Everyone"],
            }

        response = c.post("/admin-action")

    captured = capsys.readouterr()
    combined = captured.out + captured.err

    # enforce: must return 403
    assert response.status_code == 403
    # structlog event key is "rbac_denial"
    assert "rbac_denial" in combined, (
        f"Expected 'rbac_denial' in log output, got:\n{combined!r}"
    )


def test_requires_role_admin_passes_through(app, capsys):
    """An admin user must reach the view (200) and must NOT trigger rbac_denial."""
    from flask import Flask

    mini = Flask("rbac_test_admin")
    mini.config["RBAC_ADMIN_GROUPS"] = "Lab-Admins"
    mini.config["RBAC_LAB_TECH_LEAD_GROUPS"] = ""
    mini.config["RBAC_LAB_TECH_GROUPS"] = ""
    mini.config["LOGIN_DISABLED"] = False
    mini.config["SECRET_KEY"] = "test"

    @mini.route("/admin-action", methods=["POST"])
    @requires_role("admin")
    def admin_action():
        return "ok", 200

    with mini.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_identity"] = {
                "email": "admin@example.com",
                "groups": ["Lab-Admins", "Everyone"],
            }
        response = c.post("/admin-action")

    assert response.status_code == 200
    captured = capsys.readouterr().out
    assert "rbac_denial" not in captured, (
        "Admin user must not trigger an rbac_denial log line; "
        f"captured stdout: {captured!r}"
    )


# ---------------------------------------------------------------------------
# Okta groups claim extraction
# ---------------------------------------------------------------------------


def test_extract_identity_includes_groups():
    """extract_identity must include a groups list from the claims."""
    from services.okta_auth import OktaAuthService

    claims = {
        "email": "user@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "groups": ["Lab-Admins", "Everyone"],
    }
    identity = OktaAuthService.extract_identity(claims)
    assert identity["groups"] == ["Lab-Admins", "Everyone"]


def test_extract_identity_groups_defaults_to_empty():
    """extract_identity must return empty groups list when claim is absent."""
    from services.okta_auth import OktaAuthService

    claims = {
        "email": "user@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
    }
    identity = OktaAuthService.extract_identity(claims)
    assert identity["groups"] == []


# ---------------------------------------------------------------------------
# Fail-fast: unknown role at decoration time
# ---------------------------------------------------------------------------


def test_requires_role_rejects_unknown_role():
    """A typo'd role name must raise ValueError at decoration time, never
    silently degrade to a permissive lookup."""
    import pytest

    from services.rbac import requires_role

    with pytest.raises(ValueError, match="unknown role"):
        # Note: capital "A" — this would have been treated as
        # lowest-privilege under the old .get(role, len(TIERS)) lookup,
        # which silently bypassed enforcement for typos.
        requires_role("Admin")

    with pytest.raises(ValueError, match="unknown role"):
        requires_role("superuser")
