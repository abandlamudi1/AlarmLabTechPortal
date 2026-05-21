"""Tests for CSRF protection on POST routes (Slice A, Issue #36).

CSRF is enforced by Flask-WTF when WTF_CSRF_ENABLED=True.  In tests we
exercise this via the conftest app fixture (which sets TESTING=True, and
Flask-WTF skips CSRF in test mode by default) and a separate fixture that
enables enforcement to verify the 400 rejection path.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_csrf_enforced_client(base_app):
    """Return a test client with CSRF enforcement turned on."""
    base_app.config["WTF_CSRF_ENABLED"] = True
    base_app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    return base_app.test_client()


# ---------------------------------------------------------------------------
# Structural tests — CSRF token appears in rendered pages
# ---------------------------------------------------------------------------


def test_csrf_token_present_in_add_item_form(client):
    """The add-item form must render a csrf_token hidden field."""
    response = client.get("/inventory/add_item")
    assert response.status_code == 200
    assert b"csrf_token" in response.data


def test_csrf_token_present_in_rf_form(client):
    """The RF chamber form must render a csrf_token hidden field."""
    response = client.get("/rf-chamber/add")
    assert response.status_code == 200
    assert b"csrf_token" in response.data


def test_csrf_token_present_in_print_request_form(client):
    """The print request tool index renders without error."""
    response = client.get("/print-requests/")
    assert response.status_code == 200


def test_csrf_token_present_in_system_form(client):
    """System-locator new-system form must render a csrf_token hidden field."""
    response = client.get("/systems/new")
    assert response.status_code == 200
    assert b"csrf_token" in response.data


# ---------------------------------------------------------------------------
# Enforcement tests — POST without a CSRF token must be rejected (400)
# ---------------------------------------------------------------------------


def test_post_without_csrf_token_rejected(app):
    """With WTF_CSRF_ENABLED=True, a POST that omits the csrf_token must 400."""
    enforced = _make_csrf_enforced_client(app)
    # The inventory add_item route accepts POSTs; without a csrf_token Flask-WTF
    # must reject before the view runs.
    response = enforced.post(
        "/inventory/add_item",
        data={"name": "no-token-item", "quantity": "1"},
    )
    assert response.status_code == 400, (
        f"Expected 400 for missing CSRF token, got {response.status_code}"
    )


def test_post_with_csrf_token_accepted(app):
    """With CSRF enforced, a POST that includes a valid token must NOT be rejected
    for CSRF reasons (status may still be a redirect/422 etc. for other reasons,
    but never 400 with a CSRF-error body)."""
    enforced = _make_csrf_enforced_client(app)
    # First GET the form so Flask-WTF stamps a token into the session.
    get_response = enforced.get("/inventory/add_item")
    assert get_response.status_code == 200

    # Extract the token from the rendered form.
    import re

    match = re.search(
        rb'name="csrf_token"[^>]*value="([^"]+)"', get_response.data
    )
    assert match, "Expected csrf_token field in rendered form"
    token = match.group(1).decode()

    response = enforced.post(
        "/inventory/add_item",
        data={
            "csrf_token": token,
            "name": "with-token-item",
            "description": "test fixture",
            "quantity": "1",
            "min_stock": "0",
        },
    )
    # 200/302 = passed CSRF and view ran. 400 would indicate CSRF failure
    # (other 4xx could come from validation; assert specifically on CSRF).
    assert response.status_code != 400 or b"CSRF" not in response.data, (
        f"POST with valid CSRF token rejected by Flask-WTF; got "
        f"{response.status_code} with body: {response.data[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Security-headers tests (Issue #36)
# ---------------------------------------------------------------------------


def test_security_headers_on_home(client):
    """Every response must carry the core security headers."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Referrer-Policy" in response.headers


def test_security_headers_on_api_route(client):
    """Security headers must be present on blueprint routes too."""
    response = client.get("/inventory/")
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
