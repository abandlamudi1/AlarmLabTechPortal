"""Tests for /healthz and /readyz probe endpoints.

Slice B, Issue #7. Slice D, Issue #89: Redis health check.

Coverage:
  - /healthz returns 200 with {"status": "ok"} unconditionally.
  - /readyz returns 200 with per-DB status when all DBs are reachable.
  - /readyz returns 503 with degraded status when a DB probe fails.
  - /readyz includes Redis check when REDIS_URL is configured.
  - /readyz omits Redis check when REDIS_URL is not configured.
  - Both endpoints are accessible without authentication (LOGIN_DISABLED=False).
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
import redis


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_returns_json_ok(client):
    response = client.get("/healthz")
    data = response.get_json()
    assert data == {"status": "ok"}


def test_healthz_no_auth_required(app):
    """Even with LOGIN_DISABLED=False /healthz must be reachable."""
    app.config["LOGIN_DISABLED"] = False
    client = app.test_client()
    response = client.get("/healthz")
    # Without a session the login gate would redirect to /login.
    # A 200 here confirms healthz is exempt from the auth gate.
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /readyz — happy path
# ---------------------------------------------------------------------------


def test_readyz_returns_200_when_all_dbs_ok(client):
    response = client.get("/readyz")
    assert response.status_code == 200


def test_readyz_body_contains_per_db_status(client):
    response = client.get("/readyz")
    data = response.get_json()
    assert data["status"] == "ok"
    checks = data["checks"]
    for db_name in ("inventory", "rf_chamber", "checkout", "system_locator", "print_requests", "audit_log"):
        assert db_name in checks, f"Missing DB check for {db_name!r}"
        assert checks[db_name]["status"] == "ok", f"DB {db_name!r} not ok: {checks[db_name]}"


def test_readyz_no_auth_required(app):
    """readyz must also be reachable without a session cookie."""
    app.config["LOGIN_DISABLED"] = False
    client = app.test_client()
    # We only care that the probe isn't redirected to login (status != 302).
    response = client.get("/readyz")
    assert response.status_code != 302


# ---------------------------------------------------------------------------
# /readyz — failure path
# ---------------------------------------------------------------------------


def test_readyz_returns_503_on_db_failure(client):
    """When one DB probe raises, /readyz must return 503."""
    def _broken_connect(path, timeout=1.0):
        raise sqlite3.OperationalError("simulated DB failure")

    with patch("app._check_db", wraps=lambda label, db_path, timeout=1.0: (
        {"status": "error", "detail": "simulated DB failure"}
        if label == "inventory"
        else {"status": "ok"}
    )):
        response = client.get("/readyz")

    assert response.status_code == 503


def test_readyz_503_body_shows_degraded_status(client):
    with patch("app._check_db", wraps=lambda label, db_path, timeout=1.0: (
        {"status": "error", "detail": "down"}
        if label == "checkout"
        else {"status": "ok"}
    )):
        response = client.get("/readyz")

    data = response.get_json()
    assert data["status"] == "degraded"
    assert data["checks"]["checkout"]["status"] == "error"


# ---------------------------------------------------------------------------
# /readyz — Redis checks (Slice D, Issue #89)
# ---------------------------------------------------------------------------


def test_readyz_includes_redis_check_when_configured(client, app):
    """When REDIS_URL is set, /readyz includes a redis key in checks.

    Patches redis.from_url so _check_redis_readyz runs the real REDIS_URL
    gating logic rather than bypassing it entirely.
    """
    app.config["REDIS_URL"] = "redis://localhost:6379/0"
    with patch("redis.from_url") as mock_redis:
        mock_redis.return_value.ping.return_value = True
        response = client.get("/readyz")

    data = response.get_json()
    assert "redis" in data["checks"]
    assert data["checks"]["redis"]["status"] == "ok"


def test_readyz_omits_redis_check_when_unconfigured(client, app):
    """When REDIS_URL is not set, /readyz omits the redis key from checks."""
    app.config["REDIS_URL"] = None
    response = client.get("/readyz")

    data = response.get_json()
    assert "redis" not in data["checks"]
    assert response.status_code == 200


def test_readyz_returns_503_when_redis_unreachable(client, app):
    """When Redis is unreachable, /readyz returns 503 with degraded status."""
    app.config["REDIS_URL"] = "redis://localhost:6379/0"
    with patch("app._check_redis_readyz", return_value={"status": "error", "detail": "Connection refused"}):
        response = client.get("/readyz")

    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"]["status"] == "error"
    assert data["checks"]["redis"]["detail"] == "Connection refused"


def test_redis_check_catches_connection_error(app):
    """_check_redis_readyz catches redis.exceptions.ConnectionError."""
    app.config["REDIS_URL"] = "redis://localhost:9999"
    with app.app_context():
        from app import _check_redis_readyz
        with patch("redis.from_url") as mock_redis:
            mock_redis.return_value.ping.side_effect = redis.exceptions.ConnectionError("Connection refused")
            result = _check_redis_readyz()

    assert result["status"] == "error"
    assert "Connection refused" in result["detail"]


def test_redis_check_returns_none_when_url_not_set(app):
    """_check_redis_readyz returns None when REDIS_URL is not configured."""
    app.config["REDIS_URL"] = None
    with app.app_context():
        from app import _check_redis_readyz
        result = _check_redis_readyz()

    assert result is None


def test_readyz_handles_all_dbs_ok_and_redis_ok(client, app):
    """Happy path: all DBs and Redis healthy returns 200 with ok status.

    Patches redis.from_url so the real REDIS_URL gating logic is exercised.
    """
    app.config["REDIS_URL"] = "redis://localhost:6379/0"
    with patch("redis.from_url") as mock_redis:
        mock_redis.return_value.ping.return_value = True
        response = client.get("/readyz")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert all(v["status"] == "ok" for v in data["checks"].values())
