from flask import Blueprint, render_template, request, redirect, session, url_for
from sqlalchemy import select as _sa_select

from services.audit_log import log_event as _audit
from . import db
from .models import Equipment, get_session

checkout_bp = Blueprint(
    "checkout",
    __name__,
    template_folder="templates",
    static_folder="static",
)


@checkout_bp.route("/")
def dashboard():
    # Slice D-part1 spike (Issue #48): list_equipment migrated to SQLAlchemy.
    # Write routes (checkout / return) still use the raw sqlite3 layer in db.py.
    # items is converted to plain dicts so the existing template's dict-style
    # access (item['name'] etc.) continues to work without modification.
    with get_session() as sa_session:
        rows = sa_session.scalars(
            _sa_select(Equipment).order_by(Equipment.name)
        ).all()
    items = [row.as_dict() for row in rows]
    status = request.args.get("status")
    message = request.args.get("message")
    return render_template(
        "checkout_dashboard.html",
        items=items,
        status=status,
        message=message,
    )


@checkout_bp.post("/<int:item_id>/checkout")
def checkout_item(item_id: int):
    user_name = request.form.get("user_name", "")
    return_date = request.form.get("return_date", "")
    jira_link = request.form.get("jira_link", "")
    success = db.checkout_item(item_id, user_name, return_date, jira_link)
    if success:
        actor = (session.get("user_identity") or {}).get("email", "<unknown>")
        _audit(
            actor=actor,
            action="checkout.checkout",
            resource_type="equipment",
            resource_id=item_id,
            detail={"user_name": user_name, "return_date": return_date},
        )
        message = "Item checked out successfully."
        status = "success"
    else:
        message = "Unable to check out item. Confirm it is available and include a name and return date."
        status = "error"
    return redirect(url_for("checkout.dashboard", status=status, message=message))


@checkout_bp.post("/<int:item_id>/return")
def return_item(item_id: int):
    success = db.return_item(item_id)
    if success:
        actor = (session.get("user_identity") or {}).get("email", "<unknown>")
        _audit(
            actor=actor,
            action="checkout.return",
            resource_type="equipment",
            resource_id=item_id,
        )
        message = "Item returned successfully."
        status = "success"
    else:
        message = "Unable to return item."
        status = "error"
    return redirect(url_for("checkout.dashboard", status=status, message=message))
