"""Prometheus metrics instrumentation for the Lab Tech Portal.

Slice B, Issue #32 — Prometheus /metrics endpoint.

Pattern: docs/patterns/observability/audit-logging.md
(qe-architecture-ai-assisted-guide @ 81d85b9)

Design:
- Module-level metric objects are created at import time so that
  jira_service.py (and other callers) can do a simple top-level import
  without needing a Flask app context.
- init_app(app) wires PrometheusMetrics to the Flask app. It is a no-op
  when METRICS_ENABLED=False, which prevents the /metrics endpoint from
  being registered. Tests set METRICS_ENABLED=False to avoid prometheus
  global-registry accumulation across test runs.
- Active-session gauge: Flask uses stateless signed cookies — the gauge
  resets to zero on every process restart. This is an accepted limitation;
  external session storage (Slice D-part2) would allow persistence.
- Celery queue depth: declared as a stub returning 0 until Slice C ships
  celery_app.py. Do NOT block on Celery availability.
"""
from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom business metrics — declared at module level so importers (e.g.
# jira_service.py) can reference them without an app context.
# ---------------------------------------------------------------------------

_NAMESPACE = "lab_portal"

jira_task_success_total: Counter = Counter(
    f"{_NAMESPACE}_jira_task_success_total",
    "Total number of successful Jira API operations",
    ["operation"],
)

jira_task_failure_total: Counter = Counter(
    f"{_NAMESPACE}_jira_task_failure_total",
    "Total number of failed Jira API operations",
    ["operation"],
)

active_user_sessions: Gauge = Gauge(
    f"{_NAMESPACE}_active_user_sessions",
    "Number of currently active user sessions (resets on process restart — "
    "accepted limitation; Flask stateless cookie sessions have no server-side count).",
)

db_query_duration_seconds: Histogram = Histogram(
    f"{_NAMESPACE}_db_query_duration_seconds",
    "Duration of SQLite probe queries in seconds (measured at /readyz check level; "
    "per-tool DB wrapping is deferred to Slice D-part2).",
    ["db"],
)

celery_queue_depth: Gauge = Gauge(
    f"{_NAMESPACE}_celery_queue_depth",
    "Current depth of the Celery task queue (stub — always 0 until Slice C ships celery_app.py).",
)
# TODO(Slice-C): wire to celery.control.inspect().active_queues() once celery_app.py ships.
celery_queue_depth.set(0)

# ---------------------------------------------------------------------------
# Flask integration — called once at app startup.
# ---------------------------------------------------------------------------

_metrics_instance = None


def init_app(app) -> None:
    """Wire PrometheusMetrics to *app* if METRICS_ENABLED is True.

    When METRICS_ENABLED=False this function is a no-op: the /metrics route
    is never registered and prometheus_flask_exporter is never imported.
    This keeps the test suite clean (no cross-test global registry state).

    Args:
        app: The Flask application instance.
    """
    global _metrics_instance

    if not app.config.get("METRICS_ENABLED", True):
        logger.info("METRICS_ENABLED=False — /metrics endpoint suppressed.")
        return

    # Import here (not at module top) to avoid side-effects when
    # METRICS_ENABLED=False. prometheus_flask_exporter registers routes on
    # import if an app context is active, so deferring avoids surprises.
    from prometheus_flask_exporter import PrometheusMetrics  # noqa: PLC0415

    _metrics_instance = PrometheusMetrics(
        app,
        # Use the configured namespace for auto-instrumented HTTP metrics.
        default_labels={"app": "lab-tech-portal"},
        # Expose the /metrics endpoint (default path).
        path="/metrics",
        # Group routes by HTTP method + URI template (not per-parameter value).
        group_by="url_rule",
    )

    logger.info("Prometheus metrics initialised (endpoint=/metrics)")
