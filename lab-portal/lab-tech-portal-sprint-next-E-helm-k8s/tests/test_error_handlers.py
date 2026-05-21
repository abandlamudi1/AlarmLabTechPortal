"""Tests for global error handlers (Slice C, Issue #34).

Verifies:
- HTML vs JSON content negotiation based on /api/* path prefix
- request_id included in JSON payloads
- No stack traces exposed in 500 responses
- 429 and CSRF error handlers return structured responses

Test routes are registered at module-import time (before any request is
handled) to satisfy Flask 3.x's post-first-request route-registration guard.
The endpoint-uniqueness guard prevents duplicate registration when pytest
re-imports the module.
"""
import json
import pytest

from app import app as flask_app


# ---------------------------------------------------------------------------
# Register test-only boom-routes at module import time.
# Flask 3.x raises AssertionError if routes are added after the first request.
# ---------------------------------------------------------------------------

def _register_boom_routes(app):
    existing = {r.endpoint for r in app.url_map.iter_rules()}

    if "_test_404_html" not in existing:
        @app.route("/_test_404_html")
        def _test_404_html():  # pragma: no cover
            from flask import abort
            abort(404)

    if "_test_500_html" not in existing:
        @app.route("/_test_500_html")
        def _test_500_html():  # pragma: no cover
            raise RuntimeError("deliberate 500 for test")

    if "_test_api_404" not in existing:
        @app.route("/api/_test_404")
        def _test_api_404():  # pragma: no cover
            from flask import abort
            abort(404)

    if "_test_api_500" not in existing:
        @app.route("/api/_test_500")
        def _test_api_500():  # pragma: no cover
            raise RuntimeError("deliberate 500 for test")

    if "_test_api_429" not in existing:
        @app.route("/api/_test_429")
        def _test_api_429():  # pragma: no cover
            from flask import abort
            abort(429)

    if "_test_html_429" not in existing:
        @app.route("/_test_429_html")
        def _test_html_429():  # pragma: no cover
            from flask import abort
            abort(429)


# Register immediately on import, before any other test can trigger a request.
_register_boom_routes(flask_app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_no_propagate(app):
    """Test client with exception propagation disabled so 500 handlers fire.

    Flask's TESTING=True normally re-raises unhandled exceptions before the
    error handler can intercept them. Setting PROPAGATE_EXCEPTIONS=False lets
    the 500 handler run while keeping the rest of the test config intact.
    """
    prev = app.config.get("PROPAGATE_EXCEPTIONS")
    app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        yield app.test_client()
    finally:
        if prev is None:
            app.config.pop("PROPAGATE_EXCEPTIONS", None)
        else:
            app.config["PROPAGATE_EXCEPTIONS"] = prev


# ---------------------------------------------------------------------------
# 404 tests
# ---------------------------------------------------------------------------

class Test404:
    def test_html_404_returns_html_page(self, client):
        resp = client.get("/_test_404_html")
        assert resp.status_code == 404
        assert b"404" in resp.data
        assert resp.content_type.startswith("text/html")

    def test_html_404_no_stack_trace(self, client):
        resp = client.get("/_test_404_html")
        assert b"Traceback" not in resp.data
        assert b"traceback" not in resp.data

    def test_api_404_returns_json(self, client):
        resp = client.get("/api/_test_404")
        assert resp.status_code == 404
        assert resp.content_type.startswith("application/json")
        body = json.loads(resp.data)
        assert body["error"] == "Not found"
        assert body["status"] == 404

    def test_api_404_contains_request_id(self, client):
        resp = client.get("/api/_test_404", headers={"X-Request-ID": "test-id-404"})
        body = json.loads(resp.data)
        assert body["request_id"] == "test-id-404"

    def test_api_404_no_stack_trace(self, client):
        resp = client.get("/api/_test_404")
        body = json.loads(resp.data)
        assert "Traceback" not in json.dumps(body)
        assert "traceback" not in json.dumps(body)


# ---------------------------------------------------------------------------
# 500 tests
# ---------------------------------------------------------------------------

class Test500:
    def test_html_500_returns_html_page(self, client_no_propagate):
        resp = client_no_propagate.get("/_test_500_html")
        assert resp.status_code == 500
        assert b"500" in resp.data
        assert resp.content_type.startswith("text/html")

    def test_html_500_no_stack_trace(self, client_no_propagate):
        resp = client_no_propagate.get("/_test_500_html")
        assert b"Traceback" not in resp.data
        assert b"RuntimeError" not in resp.data
        assert b"deliberate 500 for test" not in resp.data

    def test_api_500_returns_json(self, client_no_propagate):
        resp = client_no_propagate.get("/api/_test_500")
        assert resp.status_code == 500
        assert resp.content_type.startswith("application/json")
        body = json.loads(resp.data)
        assert body["error"] == "Internal server error"
        assert body["status"] == 500

    def test_api_500_no_stack_trace_in_json(self, client_no_propagate):
        resp = client_no_propagate.get("/api/_test_500")
        body = json.loads(resp.data)
        raw = json.dumps(body)
        assert "Traceback" not in raw
        assert "RuntimeError" not in raw
        assert "deliberate 500 for test" not in raw

    def test_api_500_contains_request_id(self, client_no_propagate):
        resp = client_no_propagate.get("/api/_test_500", headers={"X-Request-ID": "test-id-500"})
        body = json.loads(resp.data)
        assert body["request_id"] == "test-id-500"


# ---------------------------------------------------------------------------
# 429 tests
# ---------------------------------------------------------------------------

class Test429:
    def test_api_429_returns_json(self, client):
        resp = client.get("/api/_test_429")
        assert resp.status_code == 429
        assert resp.content_type.startswith("application/json")
        body = json.loads(resp.data)
        assert body["error"] == "Rate limit exceeded"
        assert body["status"] == 429

    def test_api_429_contains_request_id(self, client):
        resp = client.get("/api/_test_429", headers={"X-Request-ID": "test-id-429"})
        body = json.loads(resp.data)
        assert body["request_id"] == "test-id-429"

    def test_html_429_returns_html(self, client):
        resp = client.get("/_test_429_html")
        assert resp.status_code == 429
        assert resp.content_type.startswith("text/html")


# ---------------------------------------------------------------------------
# CSRF error tests
# Tests call the handler directly via test_request_context to avoid routing
# complexity (no CSRF-protected POST form that's also reachable in tests).
# ---------------------------------------------------------------------------

class TestCSRFError:
    def test_csrf_error_html_returns_400(self, app):
        """CSRFError handler on an HTML path returns 400 with an HTML body."""
        from flask_wtf.csrf import CSRFError as _CSRFError
        with app.test_request_context("/_test_csrf_html", method="POST"):
            from app import csrf_error, _bind_request_logging
            _bind_request_logging()
            resp, status = csrf_error(_CSRFError("missing token"))
            assert status == 400
            # render_template returns a string; verify it looks like HTML
            assert isinstance(resp, str)
            assert "<!DOCTYPE html>" in resp or "<html" in resp

    def test_csrf_error_api_returns_json(self, app):
        """CSRF errors on /api/* paths return structured JSON 400."""
        from flask_wtf.csrf import CSRFError as _CSRFError
        with app.test_request_context("/api/some-endpoint", method="POST"):
            from app import csrf_error, _bind_request_logging
            _bind_request_logging()
            resp, status = csrf_error(_CSRFError("missing token"))
            body = json.loads(resp.get_data())
            assert status == 400
            assert body["error"] == "CSRF validation failed"
            assert body["status"] == 400

    def test_csrf_error_api_contains_request_id(self, app):
        """request_id is present in CSRF error JSON payload."""
        from flask_wtf.csrf import CSRFError as _CSRFError
        from werkzeug.test import EnvironBuilder
        builder = EnvironBuilder(
            path="/api/some-endpoint",
            method="POST",
            headers={"X-Request-ID": "csrf-test-id"},
        )
        environ = builder.get_environ()
        with app.request_context(environ):
            from app import csrf_error, _bind_request_logging
            _bind_request_logging()
            resp, status = csrf_error(_CSRFError("missing token"))
            body = json.loads(resp.get_data())
            assert body["request_id"] == "csrf-test-id"


# ---------------------------------------------------------------------------
# request_id propagation (auto-generated when header absent)
# ---------------------------------------------------------------------------

class TestRequestIdPropagation:
    def test_request_id_auto_generated_when_absent(self, client):
        resp = client.get("/api/_test_404")
        body = json.loads(resp.data)
        # Auto-generated IDs are UUIDs (36 chars with dashes).
        assert len(body["request_id"]) == 36

    def test_request_id_echoed_in_response_header(self, client):
        resp = client.get("/api/_test_404", headers={"X-Request-ID": "hdr-id-test"})
        assert resp.headers.get("X-Request-ID") == "hdr-id-test"
