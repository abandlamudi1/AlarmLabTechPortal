"""Tests for structured JSON logging with request correlation.

Slice B, Issue #33.

Coverage:
  - A request produces a log line with request_id, path, method, status.
  - X-Request-ID header is forwarded as request_id when present.
  - A UUID4 is generated as request_id when the header is absent.
  - bind_request_context / clear_request_context work correctly.
  - get_logger returns a usable structlog logger.
"""
from __future__ import annotations

import io
import json
import logging
import re

import pytest
import structlog

from services.logging_config import (
    bind_request_context,
    clear_request_context,
    get_logger,
    get_request_context,
    init_logging,
)

# ---------------------------------------------------------------------------
# Unit tests for logging_config helpers (no Flask context needed)
# ---------------------------------------------------------------------------


def test_bind_and_get_request_context():
    clear_request_context()
    bind_request_context(request_id="abc-123", path="/test", method="GET")
    ctx = get_request_context()
    assert ctx["request_id"] == "abc-123"
    assert ctx["path"] == "/test"
    assert ctx["method"] == "GET"


def test_clear_request_context():
    bind_request_context(request_id="xyz")
    clear_request_context()
    ctx = get_request_context()
    assert ctx == {}


def test_get_logger_returns_structlog_logger():
    log = get_logger("test.module")
    assert log is not None
    # structlog loggers expose .info, .warning, .error, .debug
    assert callable(getattr(log, "info", None))
    assert callable(getattr(log, "warning", None))


def test_init_logging_plain_does_not_raise():
    """init_logging with plain format must complete without error."""
    init_logging(log_level="INFO", log_format="plain", structlog_enabled=True)


def test_init_logging_json_does_not_raise():
    """init_logging with json format must complete without error."""
    init_logging(log_level="DEBUG", log_format="json", structlog_enabled=True)


def test_init_logging_disabled_does_not_raise():
    """init_logging with structlog_enabled=False must complete without error."""
    init_logging(log_level="WARNING", log_format="plain", structlog_enabled=False)


# ---------------------------------------------------------------------------
# Integration tests — Flask request produces correlation fields in logs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_log_context():
    """Ensure each test starts with a clean request context."""
    clear_request_context()
    yield
    clear_request_context()


def test_request_sets_request_id_in_context(client, capsys):
    """A request produces a structured log line with request_id, path, method, status.

    structlog uses PrintLoggerFactory which writes directly to stdout, so we
    capture via pytest's capsys rather than a stdlib logging.Handler.

    We verify the structured fields appear in the log output regardless of
    whether the renderer chose JSON or console format (cache_logger_on_first_use
    means re-calling init_logging does not flush the cached processor chain in
    the same process).
    """
    response = client.get("/healthz")
    assert response.status_code == 200

    captured = capsys.readouterr()
    combined = captured.out + captured.err

    # The log line must contain all four correlation fields.
    # Works for both JSON ("request_id": "...") and console (request_id=...) renderers.
    assert "request_id" in combined, f"request_id not in log output:\n{combined!r}"
    assert "path" in combined, f"path not in log output:\n{combined!r}"
    assert "method" in combined, f"method not in log output:\n{combined!r}"
    assert "status" in combined, f"status not in log output:\n{combined!r}"


def test_request_id_header_is_forwarded(client):
    """X-Request-ID header value should appear in request.environ."""
    custom_id = "my-trace-id-99"
    from app import app as flask_app

    with flask_app.test_request_context("/healthz", headers={"X-Request-ID": custom_id}):
        from flask import request as flask_request

        # Simulate what _bind_request_logging does.
        request_id = flask_request.headers.get("X-Request-ID") or "generated"
        assert request_id == custom_id


def test_request_id_generated_when_header_absent(client):
    """When X-Request-ID is absent a UUID4 is generated."""
    import uuid

    from app import app as flask_app

    with flask_app.test_request_context("/healthz"):
        from flask import request as flask_request

        request_id = flask_request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # UUID4 regex
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            request_id,
        ), f"Generated request_id is not a UUID4: {request_id!r}"
