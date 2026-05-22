# celery_app.py — Slice C, Issue #13 / Slice C2, Issue #17
# Pure factory module — no top-level Flask app import to avoid circular imports
# when tasks/ (Wave 2) imports celery from app.py.
# Entry-point for workers: ``celery -A app worker/beat`` (app.py exports celery).
from celery import Celery
from celery.schedules import crontab


def make_celery(app):
    """Return a Celery instance bound to *app*'s context and config.

    Only CELERY_-prefixed Flask config keys are forwarded to Celery (lowercased
    for Celery 5 compatibility).  This prevents leaking SECRET_KEY, Okta
    tokens, and other Flask-only secrets into the Celery subsystem.

    Beat schedule (Issue #17):
    - sync-jira-systems       every 15 minutes
    - check-stale-checkouts   daily at 09:00 UTC
    - backup-databases        daily at 02:00 UTC
    - cleanup-temp-uploads    weekly on Sunday at 00:00 UTC
    - purge-audit-log         daily at 03:00 UTC

    Sprint 6 Issue #90 — production worker tuning:
    - task_acks_late: task is acknowledged after completion, not on receipt.
    - worker_prefetch_multiplier: 1 = each worker fetches one task at a time (fair).
    - result_expires: TTL (seconds) before task results are evicted from the backend.
    """
    celery = Celery(
        app.import_name,
        broker=app.config["CELERY_BROKER_URL"],
        backend=app.config.get("CELERY_RESULT_BACKEND"),
        include=[
            "tasks.print_request_tasks",
            "tasks.system_locator_tasks",
            "tasks.periodic",
        ],
    )
    # Forward only CELERY_* keys (excluding CLI-only routing keys), lowercased —
    # Celery 5 requires lowercase names.  broker_url and result_backend are already
    # passed to the constructor above.  CELERY_WORKER_CONCURRENCY and CELERY_QUEUES
    # are explicitly excluded: they are CLI flags (--concurrency / -Q), not Celery
    # conf settings.  Forwarding them as worker_concurrency/queues would shadow the
    # Celery defaults in an unintended way even though the CLI flags override at
    # runtime anyway.
    celery.conf.update(
        {
            k[len("CELERY_"):].lower(): v
            for k, v in app.config.items()
            if k.startswith("CELERY_")
            and k not in (
                "CELERY_BROKER_URL",
                "CELERY_RESULT_BACKEND",
                "CELERY_WORKER_CONCURRENCY",
                "CELERY_QUEUES",
            )
        }
    )
    # Apply worker-tuning settings.  These are read by the worker process at
    # startup and do not affect the beat scheduler.
    celery.conf.update(
        task_acks_late=True,
        worker_prefetch_multiplier=app.config.get("WORKER_PREFETCH_MULTIPLIER", 1),
        result_expires=app.config.get("RESULT_EXPIRES", 86400),
    )

    # --- Slice C2, Issue #17: Beat schedule ---
    # Task names must match the ``name=`` argument on each @shared_task decorator
    # in tasks/periodic.py.  All times are UTC.
    celery.conf.beat_schedule = {
        "sync-jira-systems": {
            "task": "tasks.periodic.sync_jira_systems",
            "schedule": crontab(minute="*/15"),
        },
        "check-stale-checkouts": {
            "task": "tasks.periodic.check_stale_checkouts",
            "schedule": crontab(hour=9, minute=0),
        },
        "backup-databases": {
            "task": "tasks.periodic.backup_databases",
            "schedule": crontab(hour=2, minute=0),
        },
        "cleanup-temp-uploads": {
            "task": "tasks.periodic.cleanup_temp_uploads",
            "schedule": crontab(day_of_week=0, hour=0, minute=0),  # Sunday 00:00 UTC
        },
        "purge-audit-log": {
            "task": "tasks.periodic.purge_audit_log",
            "schedule": crontab(hour=3, minute=0),  # daily 03:00 UTC
        },
    }
    celery.conf.timezone = "UTC"

    class ContextTask(celery.Task):
        # Class attribute (not closure) — allows subclassing and avoids
        # pickling issues with some Celery serializers.
        flask_app = app

        def __call__(self, *args, **kwargs):
            with self.flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
