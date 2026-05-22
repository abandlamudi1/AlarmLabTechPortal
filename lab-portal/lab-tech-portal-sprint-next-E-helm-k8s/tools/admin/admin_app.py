"""Admin area blueprint — audit log dashboard.

Renders an admin-only HTML view over the shared audit log (services/audit_log.py)
with three additions on top of the raw event list:

  * active-user count over a rolling window (default 30 days)
  * per-action activity breakdown ("most active areas")
  * an admin-editable retention policy (days to keep events before auto-purge)

Mounted by app.py at /admin. Every route requires the 'admin' role.
Old events are removed by the scheduled tasks.periodic.purge_audit_log task
using the retention value saved here.
"""
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from services.audit_log import (
    count_active_users,
    get_activity_summary,
    get_recent_events,
    get_retention_days,
    set_retention_days,
)
from services.rbac import requires_role as _requires_role

admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
)

# Rolling window (days) used for the active-user count and activity breakdown.
_WINDOW_DAYS = 30
# Number of audit events shown per page.
_PAGE_SIZE = 50


@admin_bp.route("/audit-log")
@_requires_role("admin")
def audit_dashboard():
    """Render the audit log dashboard: stats, activity, retention, and events."""
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * _PAGE_SIZE

    events = get_recent_events(limit=_PAGE_SIZE, offset=offset)
    active_users = count_active_users(days=_WINDOW_DAYS)
    activity = get_activity_summary(days=_WINDOW_DAYS, limit=_PAGE_SIZE)
    retention_days = get_retention_days()

    status = request.args.get("status")
    message = request.args.get("message")

    return render_template(
        "audit_dashboard.html",
        events=events,
        active_users=active_users,
        activity=activity,
        retention_days=retention_days,
        window_days=_WINDOW_DAYS,
        page=page,
        page_size=_PAGE_SIZE,
        has_next=len(events) == _PAGE_SIZE,
        status=status,
        message=message,
    )


@admin_bp.post("/audit-log/retention")
@_requires_role("admin")
def update_retention():
    """Save the retention policy (days). 0 or blank means keep events forever."""
    raw = (request.form.get("retention_days") or "").strip()
    if raw == "":
        set_retention_days(None)
        return redirect(
            url_for(
                "admin.audit_dashboard",
                status="success",
                message="Retention disabled — events are kept indefinitely.",
            )
        )
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return redirect(
            url_for(
                "admin.audit_dashboard",
                status="error",
                message="Retention must be a whole number of days.",
            )
        )
    if days < 0:
        return redirect(
            url_for(
                "admin.audit_dashboard",
                status="error",
                message="Retention must be zero or a positive number of days.",
            )
        )

    set_retention_days(days if days > 0 else None)
    if days > 0:
        msg = f"Retention set to {days} day(s). Older events are purged automatically."
    else:
        msg = "Retention disabled — events are kept indefinitely."
    return redirect(url_for("admin.audit_dashboard", status="success", message=msg))
