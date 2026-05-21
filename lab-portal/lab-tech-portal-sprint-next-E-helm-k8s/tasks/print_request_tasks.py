# tasks/print_request_tasks.py — Celery async tasks for 3D Print Request Jira operations
# Sprint 5 Wave 2, Stream G, Issue #14
#
# Tasks:
#   create_jira_ticket   — create Jira issue after form submission
#   transition_jira_ticket — transition issue on status change (cancel/close)
#
# All tasks use @shared_task to avoid importing the celery instance from app.py
# (avoids circular imports).  ContextTask from celery_app.py wraps each call in
# a Flask app context, so db helpers and current_app work without extra setup.
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from celery import shared_task

from services.jira_service import JiraService, JiraServiceError

logger = logging.getLogger(__name__)

# Status values matching Stream H's enum (jira_task_status column).
_STATUS_PENDING = "pending"
_STATUS_PROCESSING = "processing"
_STATUS_SYNCED = "synced"
_STATUS_ERROR = "error"

_DEFAULT_JIRA_PRIORITY = "P4: Low"
_DEFAULT_JIRA_REQUEST_TYPE = "Other"
_DEFAULT_JIRA_ASSIGNEE = "bbrice"
_DEFAULT_JIRA_DEADLINE_DAYS = 14


# ---------------------------------------------------------------------------
# Schema-migration helper (defensive — Stream H adds these columns formally)
# ---------------------------------------------------------------------------

def _ensure_task_columns(conn) -> None:
    """Ensure jira_task_status and jira_task_id columns exist.

    Stream H (Wave 2) adds these columns via a proper migration; this guard
    makes the tasks safe to run whether or not H has landed first.
    """
    columns = {r[1] for r in conn.execute("PRAGMA table_info(print_requests)")}
    if "jira_task_status" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN jira_task_status TEXT")
    if "jira_task_id" not in columns:
        conn.execute("ALTER TABLE print_requests ADD COLUMN jira_task_id TEXT")
    conn.commit()


def _update_task_status(request_id: int, status: str, task_id: Optional[str] = None) -> None:
    """Write jira_task_status (and optionally jira_task_id) to the DB row.

    Routes through db._connect() so WAL/busy-timeout settings and the connection
    lifecycle are consistent with the rest of the codebase.  _ensure_task_columns
    is no longer called here — db._migrate_schema() runs at startup and guarantees
    the columns exist before any task fires.
    """
    from tools.print_requests import db as print_requests_db

    with print_requests_db._connect() as conn:
        if task_id is not None:
            conn.execute(
                "UPDATE print_requests SET jira_task_status = ?, jira_task_id = ? WHERE id = ?",
                (status, task_id, request_id),
            )
        else:
            conn.execute(
                "UPDATE print_requests SET jira_task_status = ? WHERE id = ?",
                (status, request_id),
            )


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def _jira_is_configured() -> bool:
    return bool(os.getenv("JIRA_URL") and os.getenv("JIRA_PAT"))


def _build_jira_summary(record) -> str:
    base = str(record.get("description") or record.get("request_type") or "3D Print Request")
    first_line = base.splitlines()[0].strip() if base else "3D Print Request"
    if len(first_line) > 80:
        first_line = f"{first_line[:77]}..."
    return (
        f"3D Print Request: {first_line}"
        if not first_line.lower().startswith("3d print request")
        else first_line
    )


def _build_jira_description(record) -> str:
    sections = [
        "3D Print Request submitted via Lab Tech Portal",
        "",
        f"Requester: {record.get('requester')}",
        f"Team: {record.get('team') or 'Not specified'}",
        f"Request type: {record.get('request_type')}",
        f"Submitted at: {record.get('created_at')}",
        "",
    ]
    description = record.get("description") or "No additional notes were provided."
    sections.append(description)
    return "\n".join(sections)


def _compute_default_deadline(created_at) -> str:
    if isinstance(created_at, str) and created_at:
        try:
            created_dt = datetime.fromisoformat(created_at)
            base_date = created_dt.date()
        except ValueError:
            base_date = date.today()
    else:
        base_date = date.today()
    return (base_date + timedelta(days=_DEFAULT_JIRA_DEADLINE_DAYS)).isoformat()


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_jira_ticket(self, request_id: int) -> dict:
    """Create a Jira issue for the given print request.

    Triggered after form submission.  Retries up to 3 times with exponential
    backoff on transient Jira failures.

    Returns a dict with ``issue_key`` on success.
    """
    from flask import current_app
    from tools.print_requests import db as print_requests_db

    _update_task_status(request_id, _STATUS_PROCESSING, task_id=self.request.id)

    record = print_requests_db.get_request(request_id)
    if not record:
        logger.error("create_jira_ticket: request_id=%d not found", request_id)
        _update_task_status(request_id, _STATUS_ERROR)
        return {"error": f"Request {request_id} not found"}

    if not _jira_is_configured():
        logger.warning(
            "create_jira_ticket: Jira not configured; skipping request_id=%d", request_id
        )
        _update_task_status(request_id, _STATUS_ERROR)
        from tools.print_requests.db import update_jira_status
        update_jira_status(request_id, jira_ticket_key=None, jira_sync_error="Jira is not configured")
        return {"error": "Jira not configured"}

    summary = _build_jira_summary(record)
    description = _build_jira_description(record)
    attachments = [
        path
        for path in (record.get("uploaded_file_path"), record.get("uploaded_image_path"))
        if path
    ]
    deadline = record.get("due_date") or _compute_default_deadline(record.get("created_at"))

    assignee = (
        current_app.config.get("PRINT_REQUESTS_DEFAULT_ASSIGNEE") or _DEFAULT_JIRA_ASSIGNEE
    )
    priority = (
        current_app.config.get("PRINT_REQUESTS_DEFAULT_PRIORITY") or _DEFAULT_JIRA_PRIORITY
    )
    request_type = (
        current_app.config.get("PRINT_REQUESTS_DEFAULT_REQUEST_TYPE") or _DEFAULT_JIRA_REQUEST_TYPE
    )

    try:
        issue_key = JiraService().create_lab_request(
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            lab_request_type=request_type,
            deadline=deadline,
            attachments=attachments or None,
        )
    except JiraServiceError as exc:
        logger.warning(
            "create_jira_ticket: Jira error for request_id=%d: %s; retrying", request_id, exc
        )
        try:
            raise self.retry(exc=exc, countdown=int(60 * (2 ** self.request.retries)))
        except self.MaxRetriesExceededError:
            logger.error(
                "create_jira_ticket: max retries exceeded for request_id=%d: %s", request_id, exc
            )
            from tools.print_requests.db import update_jira_status
            update_jira_status(request_id, jira_ticket_key=None, jira_sync_error=str(exc))
            _update_task_status(request_id, _STATUS_ERROR)
            return {"error": str(exc)}

    from tools.print_requests.db import update_jira_status
    from services.audit_log import log_event as _audit

    update_jira_status(request_id, jira_ticket_key=issue_key, jira_sync_error=None)
    _update_task_status(request_id, _STATUS_SYNCED)
    _audit(
        actor="celery-worker",
        action="print_requests.jira_sync",
        resource_type="print_request",
        resource_id=request_id,
        detail={"jira_ticket_key": issue_key},
    )
    logger.info(
        "create_jira_ticket: created %s for request_id=%d", issue_key, request_id
    )
    return {"issue_key": issue_key}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def transition_jira_ticket(
    self, issue_key: str, transition_id: str, request_id: Optional[int] = None
) -> dict:
    """Transition a Jira issue to the given state.

    Triggered on status change (cancel/close).
    Retries up to 3 times with a fixed 30-second delay.

    ``request_id`` is optional but should always be supplied by callers so that
    final-failure errors are written back to ``print_requests.jira_sync_error``
    and are visible to operators in the queue UI.

    Returns a dict with ``status`` on success.
    """
    if not _jira_is_configured():
        logger.warning(
            "transition_jira_ticket: Jira not configured; skipping %s -> %s",
            issue_key,
            transition_id,
        )
        return {"error": "Jira not configured"}

    try:
        JiraService().transition_issue(issue_key, transition_id)
    except JiraServiceError as exc:
        logger.warning(
            "transition_jira_ticket: Jira error for %s -> %s: %s; retrying",
            issue_key,
            transition_id,
            exc,
        )
        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            logger.error(
                "transition_jira_ticket: max retries exceeded for %s -> %s: %s",
                issue_key,
                transition_id,
                exc,
            )
            if request_id is not None:
                from tools.print_requests.db import update_jira_status
                update_jira_status(
                    request_id,
                    jira_ticket_key=issue_key,
                    jira_sync_error=f"Jira transition failed: {exc}",
                )
                _update_task_status(request_id, _STATUS_ERROR)
            return {"error": str(exc)}

    logger.info("transition_jira_ticket: transitioned %s via %s", issue_key, transition_id)
    return {"status": "transitioned"}
