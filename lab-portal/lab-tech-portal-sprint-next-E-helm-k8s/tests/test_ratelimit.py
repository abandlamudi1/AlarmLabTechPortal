"""Tests for rate-limiting setup (Slice A, Issue #36).

Flask-Limiter is registered in app.py. In test mode it uses an in-memory
backend.  We verify the Limiter is present and configured; hitting the limit
reliably in tests is environment-dependent so we test integration points only.
"""
from __future__ import annotations

import pytest


def test_limiter_registered_on_app(app):
    """The Flask app must have a Limiter extension registered."""
    # Flask-Limiter stores state in app.extensions['limiter']
    assert "limiter" in app.extensions


def test_default_limit_env_var(app):
    """RATELIMIT_DEFAULT config key must be present in app.config."""
    assert "RATELIMIT_DEFAULT" in app.config


def test_home_route_returns_200_under_limit(client):
    """Repeated requests under the per-minute limit must all return 200."""
    for _ in range(5):
        response = client.get("/")
        assert response.status_code == 200


def test_inventory_route_returns_200_under_limit(client):
    """Inventory list route must return 200 for a reasonable burst."""
    for _ in range(5):
        response = client.get("/inventory/")
        assert response.status_code == 200
