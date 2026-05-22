"""Admin area blueprint — audit log dashboard + account management.

Mounted by app.py at /admin. Every route requires the 'admin' role.
"""
from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from services.audit_log import (
    count_active_users,
    get_activity_summary,
    get_oldest_event_age_days,
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

_WINDOW_DAYS = 30
_PAGE_SIZE = 50
_PURGE_WARN_DAYS = 5


def _purge_warning(retention_days):
    """Return (show_warning, days_until_purge) based on oldest event age."""
    if not retention_days:
        return False, None
    oldest_age = get_oldest_event_age_days()
    if oldest_age is None:
        return False, None
    days_until_purge = retention_days - oldest_age
    if days_until_purge <= _PURGE_WARN_DAYS:
        return True, max(0, days_until_purge)
    return False, None


@admin_bp.route("/audit-log")
@_requires_role("admin")
def audit_dashboard():
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * _PAGE_SIZE

    events = get_recent_events(limit=_PAGE_SIZE, offset=offset)
    active_users = count_active_users(days=_WINDOW_DAYS)
    activity = get_activity_summary(days=_WINDOW_DAYS, limit=_PAGE_SIZE)
    retention_days = get_retention_days()

    purge_warning, purge_in_days = _purge_warning(retention_days)

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
        purge_warning=purge_warning,
        purge_in_days=purge_in_days,
    )


@admin_bp.post("/audit-log/retention")
@_requires_role("admin")
def update_retention():
    raw = (request.form.get("retention_days") or "").strip()
    if raw == "":
        set_retention_days(None)
        return redirect(url_for("admin.audit_dashboard", status="success",
                                message="Retention disabled — events are kept indefinitely."))
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return redirect(url_for("admin.audit_dashboard", status="error",
                                message="Retention must be a whole number of days."))
    if days < 0:
        return redirect(url_for("admin.audit_dashboard", status="error",
                                message="Retention must be zero or a positive number of days."))
    set_retention_days(days if days > 0 else None)
    msg = (f"Retention set to {days} day(s). Older events are purged automatically."
           if days > 0 else "Retention disabled — events are kept indefinitely.")
    return redirect(url_for("admin.audit_dashboard", status="success", message=msg))


# ---------------------------------------------------------------------------
# Account management (LOCAL_AUTH mode only)
# ---------------------------------------------------------------------------

@admin_bp.route("/accounts")
@_requires_role("admin")
def manage_accounts():
    if not current_app.config.get("LOCAL_AUTH"):
        return redirect(url_for("admin.audit_dashboard"))
    from services.local_auth import load_accounts, ROLES
    accounts = load_accounts()
    return render_template("manage_accounts.html", accounts=accounts, roles=ROLES)


@admin_bp.post("/accounts/<username>/role")
@_requires_role("admin")
def update_account_role(username: str):
    if not current_app.config.get("LOCAL_AUTH"):
        return redirect(url_for("admin.audit_dashboard"))
    from services.local_auth import load_accounts, ROLES
    import json, os
    from pathlib import Path

    new_role = request.form.get("role", "viewer")
    if new_role not in ROLES:
        return redirect(url_for("admin.manage_accounts",
                                status="error", message="Invalid role."))
    accounts = load_accounts()
    if username not in accounts:
        return redirect(url_for("admin.manage_accounts",
                                status="error", message="Account not found."))
    accounts[username]["role"] = new_role
    data_dir = current_app.config.get("DATA_DIR", "./data")
    path = Path(data_dir) / "accounts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(accounts, f, indent=2)
    return redirect(url_for("admin.manage_accounts",
                            status="success",
                            message=f"{username} is now {new_role}."))
