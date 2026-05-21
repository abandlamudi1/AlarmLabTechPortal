"""Blueprint for the Inventory tool.

DB access delegated to tools/inventory/db.py (Slice D-part1, #9).
QR PNG files are saved under DATA_DIR/generated/inventory/ (#47).
Sprint 8, Issue #29: QR storage routed through the ObjectStorage abstraction.
"""
from __future__ import annotations

import io
import os

import qrcode
from flask import Blueprint, abort, current_app, render_template, request, redirect, send_from_directory, send_file, session, url_for

from services.audit_log import log_event as _audit
from . import db as inventory_db

inventory_bp = Blueprint(
    "inventory",
    __name__,
    template_folder="templates",
    static_folder="static",
)


def _qr_dir() -> str:
    """Return the absolute path to the QR output directory, creating it if needed.

    #47: QR PNGs live under DATA_DIR/generated/inventory/ rather than the
    tool's static/ folder so they survive container restarts via the Docker
    volume mount at /data/generated.

    Used as the local fallback when no OBJECT_STORAGE is configured.
    """
    data_dir = current_app.config.get("DATA_DIR", "./data")
    qr_dir = os.path.join(data_dir, "generated", "inventory")
    os.makedirs(qr_dir, exist_ok=True)
    return qr_dir


def _generate_qr_png(item_id: int) -> bytes:
    """Return the QR code PNG for *item_id* as raw bytes."""
    img = qrcode.make(str(item_id))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@inventory_bp.route("/")
def index():
    items = inventory_db.get_items()
    return render_template("inventory_dashboard.html", items=items)


@inventory_bp.route("/add_item", methods=["GET", "POST"])
def add_item():
    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        quantity = int(request.form["quantity"])
        min_stock = int(request.form["min_stock"])

        item_id = inventory_db.add_item(name, description, quantity, min_stock)

        qr_key = f"qr_{item_id}.png"
        storage = current_app.config.get("OBJECT_STORAGE")
        if storage is not None:
            png_bytes = _generate_qr_png(item_id)
            storage.put(qr_key, png_bytes, content_type="image/png")
        else:
            # Fallback: write directly to local FS.
            img = qrcode.make(str(item_id))
            img.save(os.path.join(_qr_dir(), qr_key))

        inventory_db.set_qr_code(item_id, qr_key)

        return redirect(url_for("inventory.index"))

    return render_template("add_item.html")


@inventory_bp.route("/qr/<filename>")
def qr(filename: str):
    """Serve a QR PNG via object storage or local FS (#29).

    When the storage backend is S3, redirect to a presigned URL — but only
    after confirming no legacy local file exists for the same key (backward-
    compat for rows written before the storage abstraction landed).
    When the backend is local, serve from the legacy QR directory via
    ``send_from_directory`` whose safe-join prevents traversal.

    **Path-traversal hardening**: the route param is ``<filename>`` (single
    segment — Werkzeug rejects slashes in URL), and we additionally reject
    ``..``, embedded separators, or absolute paths in case a stored DB value
    is passed via ``redirect(url_for(...))``.
    """
    from flask import redirect as _redirect

    if (
        not filename
        or ".." in filename
        or "/" in filename
        or "\\" in filename
        or os.path.isabs(filename)
    ):
        abort(404)

    # Backward-compat: serve any legacy local file directly. This protects
    # older DB rows from 404'ing after a switch to OBJECT_STORAGE_BACKEND=s3
    # (the S3 bucket wouldn't have been populated for those rows).
    legacy_path = os.path.join(_qr_dir(), filename)
    if os.path.exists(legacy_path):
        return send_from_directory(_qr_dir(), filename, mimetype="image/png")

    storage = current_app.config.get("OBJECT_STORAGE")
    if storage is not None:
        resolved = storage.url_for(filename)
        if resolved.startswith("http://") or resolved.startswith("https://"):
            return _redirect(resolved)
        if os.path.exists(resolved):
            return send_file(resolved, mimetype="image/png")

    abort(404)


@inventory_bp.route("/scan_item", methods=["GET", "POST"])
def scan_item():
    if request.method == "POST":
        item_id = int(request.form["item_id"])
        change = int(request.form["change"])
        inventory_db.update_quantity(item_id, change)
        actor = (session.get("user_identity") or {}).get("email", "<unknown>")
        _audit(
            actor=actor,
            action="inventory.quantity_adjustment",
            resource_type="inventory_item",
            resource_id=item_id,
            detail={"change": change},
        )
        return redirect(url_for("inventory.index"))
    return render_template("scan_item.html")


def init_app(app) -> None:
    """Called by app.py to wire DATA_DIR and initialise the schema."""
    inventory_db.init_app(app)
