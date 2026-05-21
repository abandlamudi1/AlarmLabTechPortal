"""Structured JSON logging with request correlation for the Lab Tech Portal.

Slice B, Issue #33 — structured logging foundation.

Pattern: docs/patterns/observability/audit-logging.md
(qe-architecture-ai-assisted-guide @ 81d85b9)

NOTE(guide-friction F05): The pattern doc (audit-logging.md) does not address
structlog configuration directly. This implementation follows structlog's
recommended Flask integration pattern and logs the gap in docs/guide-friction.md.

Design:
- Uses structlog with contextvars-based context binding so that per-request
  fields (request_id, user_email, path, method) are automatically included in
  every log record emitted during that request, without callers needing to pass
  them explicitly.
- LOG_FORMAT=json  => structlog JSON renderer (production, Kubernetes log aggregators)
- LOG_FORMAT=plain => structlog console renderer (development, human-readable)
- STRUCTLOG_ENABLED=false => structlog is initialised but outputs stdlib text;
  useful when the log shipper doesn't accept JSON (rare, but supported).
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Per-request context variable — holds a dict that is merged into every log
# record emitted during the current request.  Flask's `g` is not used here
# because logging_config.py must remain import-safe outside a request context
# (e.g. during Celery tasks, CLI commands, and unit tests).
# ---------------------------------------------------------------------------
_request_context: ContextVar[dict[str, Any]] = ContextVar("_request_context", default={})


def bind_request_context(**kwargs: Any) -> None:
    """Merge kwargs into the current request's structlog context.

    Call once per request (in a ``before_request`` hook) to attach
    ``request_id``, ``user_email``, ``path``, and ``method``.
    """
    ctx = dict(_request_context.get())
    ctx.update(kwargs)
    _request_context.set(ctx)


def clear_request_context() -> None:
    """Reset the per-request context (call in ``teardown_request``)."""
    _request_context.set({})


def get_request_context() -> dict[str, Any]:
    """Return the current request context dict (read-only view)."""
    return dict(_request_context.get())


# ---------------------------------------------------------------------------
# Custom structlog processor: inject the per-request ContextVar into the
# event dict so it appears in every log record without explicit passing.
# ---------------------------------------------------------------------------
def _inject_request_context(
    logger: logging.Logger,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    ctx = _request_context.get()
    for key, value in ctx.items():
        event_dict.setdefault(key, value)
    return event_dict


# ---------------------------------------------------------------------------
# Public initialisation — called once at app startup via init_app().
# ---------------------------------------------------------------------------
def init_logging(*, log_level: str = "INFO", log_format: str = "plain", structlog_enabled: bool = True) -> None:
    """Configure stdlib root logger + structlog processors.

    Args:
        log_level: One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
        log_format: ``"plain"`` (dev console) or ``"json"`` (production JSON).
        structlog_enabled: When False, structlog still emits records through
            ``PrintLoggerFactory`` to stdout but without the structlog-specific
            processor chain — useful when an operator wants to bypass the
            structured renderers entirely and inspect raw event dicts.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    if structlog_enabled and log_format == "json":
        formatter = logging.Formatter("%(message)s")
    else:
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    # If a runtime/test has already configured the root logger, update the
    # existing handlers' formatter+level rather than no-op'ing. This keeps
    # init_logging meaningful in pytest contexts where pytest installs its
    # own handler before our setup runs.
    if root.handlers:
        for existing in root.handlers:
            existing.setFormatter(formatter)
            existing.setLevel(level)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.setLevel(level)
        root.addHandler(handler)

    if not structlog_enabled:
        # Structlog configured as a pass-through — no custom processors.
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(),
        )
        return

    # Shared processors applied regardless of output format.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_context,
        structlog.stdlib.add_log_level,
        # add_logger_name requires a stdlib logger; safe only with
        # stdlib-bound loggers (not PrintLogger).  We bind the name via
        # get_logger(name) instead — structlog carries it as "logger" key
        # when the factory creates a named PrintLogger.
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a structlog logger bound to *name*.

    Callers that previously used ``logging.getLogger(__name__)`` can drop-in
    replace with ``get_logger(__name__)`` and gain structured context.
    """
    return structlog.get_logger(name)
