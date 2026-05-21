# tasks/system_locator_tasks.py — Celery async task for System Locator Jira import
# Sprint 5 Wave 2, Stream G, Issue #15
#
# Task:
#   sync_jira_import — perform the blocking Jira → System Locator apply() call
#                      in the background instead of blocking the HTTP request.
#
# Uses @shared_task to avoid circular imports.  ContextTask from celery_app.py
# wraps the call in a Flask app context automatically.
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_jira_import(
    self,
    project_keys: Optional[List[str]],
    start_date_iso: Optional[str],
    end_date_iso: Optional[str],
    issue_keys: Optional[List[str]],
) -> Dict:
    """Run JiraImportService.apply() asynchronously.

    Arguments are plain JSON-serialisable values (ISO date strings rather than
    datetime objects) so Celery can serialise them safely.

    On transient Jira failures the task retries up to 3 times with exponential
    backoff.  On success it returns a summary dict with created/updated/skipped
    counts.
    """
    from flask import current_app
    from datetime import datetime

    from tools.system_locator.jira_import_service import (
        JiraImportError,
        JiraPermissionError,
    )
    from tools.system_locator.system_locator_app import build_import_service

    # Deserialise date strings back to datetime objects.
    start_date = datetime.fromisoformat(start_date_iso) if start_date_iso else None
    end_date = datetime.fromisoformat(end_date_iso) if end_date_iso else None

    # Build the import service via the shared helper.  This keeps construction
    # logic in one place; _get_import_service() in system_locator_app.py wraps
    # the same call with an app-level cache for the HTTP path.
    service = build_import_service(current_app.config)

    try:
        result = service.apply(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            issue_keys=issue_keys,
        )
    except (JiraPermissionError, JiraImportError) as exc:
        logger.warning(
            "sync_jira_import: Jira error (attempt %d): %s; retrying",
            self.request.retries + 1,
            exc,
        )
        try:
            raise self.retry(exc=exc, countdown=int(60 * (2 ** self.request.retries)))
        except self.MaxRetriesExceededError:
            logger.error("sync_jira_import: max retries exceeded: %s", exc)
            return {"error": str(exc), "created": 0, "updated": 0, "skipped": 0}

    summary = {
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
    }
    logger.info("sync_jira_import: completed — %s", summary)
    return summary
