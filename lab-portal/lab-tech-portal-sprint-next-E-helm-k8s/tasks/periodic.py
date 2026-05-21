# tasks/periodic.py — Slice C2, Issue #17
# Celery Beat periodic tasks.
#
# All four tasks use ``shared_task`` to avoid a circular import with app.py
# (app.py creates the celery instance; importing it here would create a cycle).
# The ContextTask base class installed by celery_app.make_celery ensures every
# task runs inside a Flask app context, so ``current_app``, DB modules, etc.
# are available without any extra wiring.
#
# Module-level code that touches I/O MUST be guarded with the TESTING guard
# (Wave 1 Friction 1).  Here, all I/O happens inside task function bodies, so
# no guard is needed at module scope.
from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from celery import shared_task
from flask import current_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Return the configured DATA_DIR as a Path (falls back to ./data)."""
    return Path(current_app.config.get("DATA_DIR", "./data"))


# ---------------------------------------------------------------------------
# Task 1 — Sync Jira lab requests into System Locator (every 15 minutes)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, name="tasks.periodic.sync_jira_systems")
def sync_jira_systems(self):  # type: ignore[override]
    """Auto-import new Jira Lab Request issues into System Locator.

    Uses the same service layer as the web UI so the business logic is not
    duplicated.  The task is idempotent: the import service uses ``upsert``
    semantics (create or update by Jira key).
    """
    try:
        # Import lazily inside the task to keep the module side-effect-free.
        from tools.system_locator.system_locator_app import _get_import_service

        service = _get_import_service()
        result = service.apply()
        logger.info(
            "sync_jira_systems: created=%d updated=%d skipped=%d",
            result.created,
            result.updated,
            result.skipped,
        )
        return {
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
        }
    except Exception as exc:
        logger.error("sync_jira_systems failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Task 2 — Flag stale checkouts (daily at 09:00 UTC)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, name="tasks.periodic.check_stale_checkouts")
def check_stale_checkouts(self):  # type: ignore[override]
    """Flag equipment whose return_date is in the past and status is checked out.

    Logs a warning for each stale item.  A future wave will add push
    notifications; for now the warnings are visible in Celery worker logs and
    any connected log aggregator.
    """
    try:
        from tools.checkout.db import list_equipment

        today = datetime.now(UTC).date().isoformat()
        stale = []
        for row in list_equipment():
            if (
                row["checked_out_by"]
                and row["return_date"]
                and row["return_date"] < today
            ):
                stale.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "checked_out_by": row["checked_out_by"],
                        "return_date": row["return_date"],
                        "days_overdue": (
                            datetime.fromisoformat(today)
                            - datetime.fromisoformat(row["return_date"])
                        ).days,
                    }
                )

        if stale:
            for item in stale:
                logger.warning(
                    "STALE CHECKOUT: '%s' (id=%s) checked out by '%s', "
                    "return_date=%s (%d day(s) overdue)",
                    item["name"],
                    item["id"],
                    item["checked_out_by"],
                    item["return_date"],
                    item["days_overdue"],
                )
        else:
            logger.info("check_stale_checkouts: no stale items found")

        return {"stale_count": len(stale), "items": stale}
    except Exception as exc:
        logger.error("check_stale_checkouts failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Task 3 — Back up all 5 SQLite databases (daily at 02:00 UTC)
# ---------------------------------------------------------------------------

# File names match what each tool's init_app() writes under DATA_DIR/db/.
_SQLITE_DB_NAMES = [
    "checkout.db",
    "inventory.db",
    "print_requests.db",
    "systems.db",
    "rf_chambers.db",
]


@shared_task(bind=True, max_retries=3, name="tasks.periodic.backup_databases")
def backup_databases(self):  # type: ignore[override]
    """Copy all SQLite database files to a timestamped backup directory.

    Backup layout::

        DATA_DIR/backups/<YYYY-MM-DD>/checkout.db
        DATA_DIR/backups/<YYYY-MM-DD>/inventory.db
        …

    The task is idempotent: running it twice on the same day overwrites the
    earlier backup for that date (last-write-wins, which is safe for daily
    backups).
    """
    try:
        data_dir = _data_dir()
        db_dir = data_dir / "db"
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        backup_dir = data_dir / "backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=True)

        copied: list[str] = []
        missing: list[str] = []
        for name in _SQLITE_DB_NAMES:
            src = db_dir / name
            if not src.exists():
                logger.warning("backup_databases: source file not found: %s", src)
                missing.append(name)
                continue
            dst = backup_dir / name
            shutil.copy2(src, dst)
            logger.info("backup_databases: copied %s -> %s", src, dst)
            copied.append(name)

        logger.info(
            "backup_databases: backup complete — %d copied, %d missing",
            len(copied),
            len(missing),
        )
        return {"backup_dir": str(backup_dir), "copied": copied, "missing": missing}
    except Exception as exc:
        logger.error("backup_databases failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=120)


# ---------------------------------------------------------------------------
# Task 4 — Clean up orphaned temp upload files (weekly on Sunday)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, name="tasks.periodic.cleanup_temp_uploads")
def cleanup_temp_uploads(self):  # type: ignore[override]
    """Remove orphaned files from the print-request upload staging directory.

    A file is considered orphaned when it is no longer referenced by any
    active print-request record in the database.  Only files directly inside
    the configured upload folder are inspected (sub-directories are skipped).

    The task is idempotent.
    """
    try:
        from tools.print_requests.db import list_requests as _list_print_requests

        upload_folder = current_app.config.get("PRINT_REQUESTS_UPLOAD_FOLDER") or str(
            _data_dir() / "uploads"
        )
        upload_path = Path(upload_folder)

        if not upload_path.exists():
            logger.info("cleanup_temp_uploads: upload folder does not exist, nothing to clean")
            return {"removed": [], "upload_folder": str(upload_path)}

        # Collect filenames that are still referenced by active print-request
        # records.  The DB stores the value as a relative path fragment of the
        # form "<uuid>_<secure_filename>" (no directory prefix for the root
        # upload folder), so os.path.basename() normalises both cases.
        referenced: set[str] = set()
        try:
            for req in _list_print_requests():
                file_path = req.get("uploaded_file_path") if isinstance(req, dict) else getattr(req, "uploaded_file_path", None)
                if file_path:
                    referenced.add(os.path.basename(str(file_path)))
        except Exception as db_exc:  # pragma: no cover — defensive
            logger.warning("cleanup_temp_uploads: could not query print_requests DB: %s", db_exc)

        removed: list[str] = []
        for entry in upload_path.iterdir():
            if not entry.is_file():
                continue
            if entry.name not in referenced:
                try:
                    entry.unlink()
                    logger.info("cleanup_temp_uploads: removed orphan %s", entry.name)
                    removed.append(entry.name)
                except OSError as rm_exc:
                    logger.warning("cleanup_temp_uploads: could not remove %s: %s", entry.name, rm_exc)

        logger.info(
            "cleanup_temp_uploads: removed %d orphaned file(s) from %s",
            len(removed),
            upload_folder,
        )
        return {"removed": removed, "upload_folder": str(upload_path)}
    except Exception as exc:
        logger.error("cleanup_temp_uploads failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60)
