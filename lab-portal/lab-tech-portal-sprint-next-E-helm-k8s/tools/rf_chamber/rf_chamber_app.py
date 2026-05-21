"""Blueprint for the RF Chamber tool.

DB access delegated to tools/rf_chamber/db.py (Slice D-part1, #9).

QR code note (#47): RF Chamber generates QR codes as inline base64 data URIs
(_qr_code_data() below). No PNG files are written to disk, so the DATA_DIR
QR path centralisation in #47 does not apply to this tool. The QR data URI is
computed on every dashboard request and never persisted.
"""
from __future__ import annotations

import base64
import io
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

import qrcode

from services.audit_log import log_event as _audit
from . import db as rf_db

rf_chamber_bp = Blueprint(
    "rf_chamber",
    __name__,
    template_folder="templates",
    static_folder="static",
)

ACCESSORY_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("exhaust_fan", "Exhaust Fan"),
    ("usb_port", "USB Port"),
    ("ethernet_port", "Ethernet Port"),
    ("sma_antanae", "SMA Antanae"),
    ("bnc_connector", "BNC Connector"),
    ("power_strip", "Power Strip w/ 6 outlets"),
)


def _build_chamber_link(barcode: str) -> str:
    """Produce a stable edit URL, honoring an optional configured base URL."""
    base_url = current_app.config.get("RF_CHAMBER_BASE_URL", "").strip()
    if base_url:
        normalized_base = base_url.rstrip("/")
        path = url_for("rf_chamber.edit_chamber", barcode=barcode)
        return f"{normalized_base}{path}"
    return url_for("rf_chamber.edit_chamber", barcode=barcode, _external=True)


def _qr_code_data(url: str) -> str:
    """Return a data URI containing a QR code PNG for the supplied URL.

    QR codes for RF Chamber are generated as inline base64 data URIs — no
    files are written to disk. See module docstring for rationale.
    """
    try:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:  # pragma: no cover - defensive logging path
        current_app.logger.error(
            "qr_generation_failure",
            extra={
                "event": "qr_generation_failure",
                "barcode_url": url,
                "error_type": exc.__class__.__name__,
            },
            exc_info=exc,
        )
        raise


def _collect_form(form_data) -> Tuple[Dict[str, str], List[Dict[str, Any]], str]:
    chamber = {
        "barcode": form_data.get("barcode", "").strip().upper(),
        "size": form_data.get("size", "").strip(),
        "purpose": form_data.get("purpose", "").strip(),
        "location": form_data.get("location", "").strip(),
        "owner": form_data.get("owner", "").strip(),
    }

    accessories: List[Dict[str, Any]] = []
    selected_entries: List[str] = []
    for slug, label in ACCESSORY_OPTIONS:
        checked = form_data.get(f"acc_{slug}") == "on"
        qty_raw = form_data.get(f"acc_{slug}_qty", "1").strip()
        qty = int(qty_raw) if qty_raw.isdigit() else 1
        qty = max(1, min(qty, 10))
        accessories.append({"slug": slug, "label": label, "checked": checked, "qty": qty})
        if checked:
            entry = label if qty == 1 else f"{label} x{qty}"
            selected_entries.append(entry)

    other_ports = form_data.get("ports_other", "").strip()
    if other_ports:
        selected_entries.append(other_ports)

    chamber["ports"] = "; ".join(selected_entries)
    return chamber, accessories, other_ports


def _default_accessories() -> List[Dict[str, Any]]:
    return [
        {"slug": slug, "label": label, "checked": False, "qty": 1}
        for slug, label in ACCESSORY_OPTIONS
    ]


def _accessories_from_ports(ports: str) -> Tuple[List[Dict[str, Any]], str]:
    states = _default_accessories()
    if not ports:
        return states, ""

    entries = [part.strip() for part in ports.split(";") if part.strip()]
    remaining = entries.copy()

    for state in states:
        label = state["label"]
        found_entry: Optional[str] = None
        for entry in list(remaining):
            if entry.lower().startswith(label.lower()):
                suffix = entry[len(label) :].strip()
                qty = 1
                if suffix.lower().startswith("x"):
                    number = suffix[1:].strip()
                    if number.isdigit():
                        qty = max(1, min(int(number), 10))
                state["checked"] = True
                state["qty"] = qty
                found_entry = entry
                break
        if found_entry:
            remaining.remove(found_entry)

    other_ports = "; ".join(remaining)
    return states, other_ports


def _validate(chamber: Dict[str, str]) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    if not chamber["barcode"]:
        errors["barcode"] = "Chamber ID is required."
    if not chamber["size"]:
        errors["size"] = "Size is required."
    return errors


STATUS_MESSAGES: Dict[str, Tuple[str, str]] = {
    "added": ("RF chamber added.", "success"),
    "updated": ("RF chamber updated.", "success"),
    "deleted": ("RF chamber deleted.", "success"),
}


@rf_chamber_bp.route("/")
def dashboard():
    status_code = request.args.get("status", "")
    message: Optional[str] = None
    category: str = ""
    if status_code in STATUS_MESSAGES:
        message, category = STATUS_MESSAGES[status_code]
    error_message = request.args.get("error")
    if error_message:
        message = error_message
        category = "error"
    chambers = rf_db.list_chambers()
    for chamber in chambers:
        edit_url = _build_chamber_link(chamber["barcode"])
        chamber["edit_url"] = edit_url
        chamber["qr_code_data"] = _qr_code_data(edit_url)
    return render_template(
        "rf_dashboard.html",
        chambers=chambers,
        message=message,
        category=category,
    )


@rf_chamber_bp.route("/add", methods=["GET", "POST"])
def add_chamber():
    errors: Dict[str, str] = {}
    chamber = {
        "barcode": "",
        "size": "",
        "ports": "",
        "purpose": "",
        "location": "",
        "owner": "",
    }
    accessories = _default_accessories()
    other_ports = ""
    if request.method == "POST":
        chamber, accessories, other_ports = _collect_form(request.form)
        errors = _validate(chamber)
        if not errors:
            try:
                rf_db.insert_chamber(chamber)
            except sqlite3.IntegrityError:
                errors["barcode"] = "Chamber ID already exists."
            else:
                return redirect(url_for("rf_chamber.dashboard", status="added"))
    return render_template(
        "rf_form.html",
        mode="add",
        chamber=chamber,
        errors=errors,
        accessories=accessories,
        other_ports=other_ports,
    )


@rf_chamber_bp.route("/edit/<barcode>", methods=["GET", "POST"])
def edit_chamber(barcode: str):
    existing = rf_db.fetch_chamber(barcode)
    if not existing:
        return redirect(url_for("rf_chamber.dashboard", error="Chamber not found."))
    errors: Dict[str, str] = {}
    chamber = existing
    accessories, other_ports = _accessories_from_ports(existing.get("ports", ""))
    if request.method == "POST":
        if request.form.get("clear_all") == "true":
            chamber = {
                **existing,
                "ports": "",
                "purpose": "",
                "location": "",
                "owner": "",
            }
            accessories = _default_accessories()
            other_ports = ""
        else:
            payload, accessories, other_ports = _collect_form(request.form)
            errors = _validate(payload)
            if not errors:
                try:
                    rf_db.update_chamber(barcode, payload)
                except sqlite3.IntegrityError:
                    errors["barcode"] = "Chamber ID already exists."
                else:
                    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
                    _audit(
                        actor=actor,
                        action="rf_chamber.edit",
                        resource_type="rf_chamber",
                        resource_id=barcode,
                        detail={"new_barcode": payload.get("barcode")},
                    )
                    return redirect(url_for("rf_chamber.dashboard", status="updated"))
            chamber = payload
    return render_template(
        "rf_form.html",
        mode="edit",
        chamber=chamber,
        errors=errors,
        accessories=accessories,
        other_ports=other_ports,
    )


@rf_chamber_bp.route("/delete/<barcode>", methods=["POST"])
def delete_chamber(barcode: str):
    rf_db.delete_chamber(barcode)
    return redirect(url_for("rf_chamber.dashboard", status="deleted"))


def init_app(app) -> None:
    """Called by app.py to wire DATA_DIR and initialise the schema + seed data."""
    rf_db.init_app(app)
