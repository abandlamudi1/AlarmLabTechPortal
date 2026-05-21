"""Tests for the OpenAPI documentation endpoint (Slice H, Issue #53).

Verifies:
  - /api/v1/docs/ serves Swagger UI HTML when SWAGGER_ENABLED is active
  - /api/v1/docs/openapi.json returns a valid OpenAPI spec
  - All expected /api/v1/ endpoints are present in the spec
"""
from __future__ import annotations

import pytest


@pytest.fixture
def swagger_app(app):
    """App fixture with SWAGGER_ENABLED=True and flasgger mounted.

    The Flask app object is a module-level singleton shared across tests.
    We mount flasgger at most once per process: if the 'flasgger' blueprint
    is already registered (e.g. app.py registered it because debug=True, or a
    previous test run mounted it), we skip re-registration to avoid the
    "already registered" ValueError.
    """
    from flasgger import Swagger

    # Check whether flasgger has already been registered on this app instance.
    if "flasgger" not in app.blueprints:
        _SWAGGER_TEMPLATE = {
            "info": {
                "title": "Lab Tech Portal API",
                "version": "1.0.0",
            },
            "basePath": "/api/v1",
            "schemes": ["http"],
        }
        Swagger(
            app,
            template=_SWAGGER_TEMPLATE,
            config={
                "headers": [],
                "specs": [
                    {
                        "endpoint": "api_v1_spec_test",
                        "route": "/api/v1/docs/openapi.json",
                        "rule_filter": lambda rule: rule.rule.startswith("/api/v1"),
                        "model_filter": lambda tag: True,
                    }
                ],
                "static_url_path": "/api/v1/docs/static",
                "swagger_ui": True,
                "specs_route": "/api/v1/docs/",
            },
        )
    return app


@pytest.fixture
def swagger_client(swagger_app):
    return swagger_app.test_client()


# ---------------------------------------------------------------------------
# OpenAPI spec endpoint
# ---------------------------------------------------------------------------


def test_openapi_json_returns_200(swagger_client):
    """GET /api/v1/docs/openapi.json must return HTTP 200."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    assert resp.status_code == 200


def test_openapi_json_is_valid_json(swagger_client):
    """The spec endpoint must return parseable JSON."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    data = resp.get_json()
    assert data is not None


def test_openapi_spec_has_info_block(swagger_client):
    """The spec must contain an info block with title and version."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    data = resp.get_json()
    assert "info" in data
    assert "title" in data["info"]
    assert "version" in data["info"]


def test_openapi_spec_has_paths(swagger_client):
    """The spec must contain a non-empty paths object."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    data = resp.get_json()
    assert "paths" in data
    assert len(data["paths"]) > 0


def test_openapi_spec_covers_inventory(swagger_client):
    """Inventory endpoints must include both GET and POST /api/v1/inventory/items."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    inventory_items = next(
        (v for k, v in paths.items() if k.endswith("/inventory/items")), None
    )
    assert inventory_items is not None, "Expected /api/v1/inventory/items in spec"
    assert "get" in inventory_items, "Expected GET /api/v1/inventory/items in spec"
    assert "post" in inventory_items, "Expected POST /api/v1/inventory/items in spec"


def test_openapi_spec_covers_checkout(swagger_client):
    """Checkout equipment list must appear at GET /api/v1/checkout/equipment."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    checkout_equipment = next(
        (v for k, v in paths.items() if k.endswith("/checkout/equipment")), None
    )
    assert checkout_equipment is not None, "Expected /api/v1/checkout/equipment in spec"
    assert "get" in checkout_equipment, "Expected GET /api/v1/checkout/equipment in spec"


def test_openapi_spec_covers_print_requests(swagger_client):
    """Print-requests endpoints must include both GET and POST methods."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    pr_path = next(
        (v for k, v in paths.items() if "print-requests" in k and not "<" in k), None
    )
    assert pr_path is not None, "Expected /api/v1/print-requests in spec"
    assert "get" in pr_path, "Expected GET /api/v1/print-requests in spec"
    assert "post" in pr_path, "Expected POST /api/v1/print-requests in spec"


def test_openapi_spec_covers_systems(swagger_client):
    """Systems list endpoint must appear at GET /api/v1/systems."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    sys_path = next(
        (v for k, v in paths.items() if k.endswith("/systems")), None
    )
    assert sys_path is not None, "Expected /api/v1/systems in spec"
    assert "get" in sys_path, "Expected GET /api/v1/systems in spec"


def test_openapi_spec_covers_rf_chambers(swagger_client):
    """RF chambers list endpoint must appear at GET /api/v1/rf-chambers."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    rf_path = next(
        (v for k, v in paths.items() if k.endswith("/rf-chambers")), None
    )
    assert rf_path is not None, "Expected /api/v1/rf-chambers in spec"
    assert "get" in rf_path, "Expected GET /api/v1/rf-chambers in spec"


def test_openapi_spec_covers_audit_log(swagger_client):
    """Audit log endpoint must appear at GET /api/v1/audit-log."""
    resp = swagger_client.get("/api/v1/docs/openapi.json")
    paths = resp.get_json().get("paths", {})
    audit_path = next(
        (v for k, v in paths.items() if k.endswith("/audit-log")), None
    )
    assert audit_path is not None, "Expected /api/v1/audit-log in spec"
    assert "get" in audit_path, "Expected GET /api/v1/audit-log in spec"


# ---------------------------------------------------------------------------
# Swagger UI
# ---------------------------------------------------------------------------


def test_swagger_ui_returns_200(swagger_client):
    """GET /api/v1/docs/ must return HTTP 200 when SWAGGER_ENABLED."""
    resp = swagger_client.get("/api/v1/docs/")
    assert resp.status_code == 200


def test_swagger_ui_is_html(swagger_client):
    """The Swagger UI endpoint must return HTML content."""
    resp = swagger_client.get("/api/v1/docs/")
    content_type = resp.content_type or ""
    assert "text/html" in content_type
