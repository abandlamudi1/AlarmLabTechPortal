"""Blueprint providing the 3D Print Requests tool."""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from services.audit_log import log_event as _audit
from . import db
from services.jira_service import JiraService, JiraServiceError
from tasks.print_request_tasks import (
    create_jira_ticket as _create_jira_ticket_task,
    transition_jira_ticket as _transition_jira_ticket_task,
)

print_requests_bp = Blueprint(
    "print_requests",
    __name__,
    template_folder="templates",
    static_folder="static",
)

_ALLOWED_EXTENSIONS = {"stl", "3mf"}
_ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
_PRINT_STATUS_OPTIONS = ("Design", "Printing", "Cancelled", "Closed")
_CLOSED_STATUSES = {"Cancelled", "Closed"}
_DEFAULT_JIRA_PRIORITY = "P4: Low"
_DEFAULT_JIRA_REQUEST_TYPE = "Other"
_DEFAULT_JIRA_ASSIGNEE = "bbrice"
_DEFAULT_JIRA_DEADLINE_DAYS = 14


MODEL_LIBRARY: List[Dict[str, object]] = [
    {
        "slug": "doorbell-770-desk",
        "name": "Doorbell 770 Holder – Desk Mount",
        "category": "doorbell_holders",
        "category_label": "Doorbell holders",
        "category_image": "img/category-doorbell.svg",
        "device": "770",
        "device_label": "Doorbell 770",
        "device_image": "img/device-doorbell-770.svg",
        "variant": "desk",
        "variant_label": "Desk mounted",
        "variant_image": "img/variant-doorbell-770-desk.svg",
        "description": "Cradle that secures the Doorbell 770 unit to flat desk surfaces.",
        "images": ["img/doorbell-770-table.png"],
    },
    {
        "slug": "doorbell-770-glass",
        "name": "Doorbell 770 Holder – Glass Mount",
        "category": "doorbell_holders",
        "category_label": "Doorbell holders",
        "category_image": "img/category-doorbell.svg",
        "device": "770",
        "device_label": "Doorbell 770",
        "device_image": "img/device-doorbell-770.svg",
        "variant": "glass",
        "variant_label": "Glass mounted",
        "variant_image": "img/variant-doorbell-770-glass.svg",
        "description": "Low-profile suction mount for glass-walled pods and demo rooms.",
        "images": [
            "img/doorbell-770-glass-front.png",
            "img/doorbell-770-glass-back.png",
        ],
    },
    {
        "slug": "doorbell-770-pegboard",
        "name": "Doorbell 770 Holder – Pegboard",
        "category": "doorbell_holders",
        "category_label": "Doorbell holders",
        "category_image": "img/category-doorbell.svg",
        "device": "770",
        "device_label": "Doorbell 770",
        "device_image": "img/device-doorbell-770.svg",
        "variant": "pegboard",
        "variant_label": "Pegboard mounted",
        "variant_image": "img/variant-doorbell-770-pegboard.svg",
        "description": "Pegboard-ready mounting bracket for the Doorbell 770 demo units.",
        "images": [
            "img/doorbell-770-pegboard-front.png",
            "img/doorbell-770-pegboard-back.png",
        ],
    },
    {
        "slug": "doorbell-780b-pegboard",
        "name": "Doorbell 780B Holder – Pegboard",
        "category": "doorbell_holders",
        "category_label": "Doorbell holders",
        "category_image": "img/category-doorbell.svg",
        "device": "780B",
        "device_label": "Doorbell 780B",
        "device_image": "img/device-doorbell-780b.svg",
        "variant": "pegboard",
        "variant_label": "Pegboard mounted",
        "variant_image": "img/variant-doorbell-780b-pegboard.svg",
        "description": "Pegboard-compatible holster for rapid endurance swapping.",
        "images": ["img/variant-doorbell-780b-pegboard.svg"],
    },
    {
        "slug": "hook-cable-wide",
        "name": "Wide Cable Hook",
        "category": "hooks_hangers",
        "category_label": "Hooks / hangers",
        "category_image": "img/category-hooks.svg",
        "device": "cable_hook",
        "device_label": "Universal cable hook",
        "device_image": "img/device-cable-hook.svg",
        "variant": "wide",
        "variant_label": "Wide opening",
        "variant_image": "img/variant-hook-wide.svg",
        "description": "Keeps thick harness bundles staged on pegboards without kinking.",
        "images": ["img/variant-hook-wide.svg"],
    },
    {
        "slug": "enclosure-sensor-compact",
        "name": "Sensor Module Enclosure – Compact",
        "category": "enclosures",
        "category_label": "Enclosures",
        "category_image": "img/category-enclosure.svg",
        "device": "sensor_module",
        "device_label": "Sensor module",
        "device_image": "img/device-sensor-module.svg",
        "variant": "compact",
        "variant_label": "Compact",
        "variant_image": "img/variant-enclosure-compact.svg",
        "description": "Snaps around the sensor board for airflow testing rigs.",
        "images": ["img/variant-enclosure-compact.svg"],
    },
    {
        "slug": "other-calibration-jig",
        "name": "Calibration Spacer Jig",
        "category": "other",
        "category_label": "Other",
        "category_image": "img/category-other.svg",
        "device": "calibration",
        "device_label": "Calibration tooling",
        "device_image": "img/device-calibration.svg",
        "variant": "spacer",
        "variant_label": "Spacer",
        "variant_image": "img/variant-calibration-spacer.svg",
        "description": "Reusable spacer for lining up camera assemblies during QA.",
        "images": ["img/variant-calibration-spacer.svg"],
    },
]

DEVICE_LIBRARY: List[Dict[str, object]] = [
    {
        "key": "770",
        "name": "Doorbell 770",
        "description": "Cradle options for Doorbell 770 demo units.",
        "tags": ["Doorbell"],
    },
    {
        "key": "775",
        "name": "Doorbell 775",
        "description": "Device-specific cradle options for Doorbell 775.",
        "tags": ["Doorbell"],
    },
    {
        "key": "780B",
        "name": "Doorbell 780B",
        "description": "Rapid-swap cradles and lab-ready holders for Doorbell 780B.",
        "tags": ["Doorbell"],
    },
    {
        "key": "750",
        "name": "Doorbell 750",
        "description": "Docking cradles and supports for Doorbell 750 units.",
        "tags": ["Doorbell"],
    },
    {
        "key": "755",
        "name": "Doorbell 755",
        "description": "Cradle variants and fixtures for Doorbell 755 testing.",
        "tags": ["Doorbell"],
    },
]

MODEL_INDEX = {entry["slug"]: entry for entry in MODEL_LIBRARY}


def _build_hierarchy() -> Dict[str, Dict[str, object]]:
    hierarchy: Dict[str, Dict[str, object]] = {}
    for model in MODEL_LIBRARY:
        category_entry = hierarchy.setdefault(
            model["category"],
            {
                "label": model["category_label"],
                "image": model.get("category_image"),
                "devices": {},
            },
        )
        device_entry = category_entry["devices"].setdefault(
            model["device"],
            {
                "label": model["device_label"],
                "image": model.get("device_image"),
                "variants": {},
            },
        )
        device_entry["variants"][model["variant"]] = {
            "label": model["variant_label"],
            "image": model.get("variant_image"),
            "slug": model["slug"],
            "name": model["name"],
        }
    return hierarchy


MODEL_HIERARCHY = _build_hierarchy()


def _build_model_devices() -> List[Dict[str, object]]:
    devices: Dict[str, Dict[str, object]] = {}
    for entry in MODEL_LIBRARY:
        device_key = str(entry.get("device")) if entry.get("device") else entry["slug"]
        bucket = devices.setdefault(
            device_key,
            {
                "key": device_key,
                "label": entry.get("device_label") or entry.get("name"),
                "variants": [],
            },
        )
        bucket["variants"].append(
            {
                "value": entry["slug"],
                "label": entry.get("variant_label") or entry.get("name"),
            }
        )

    ordered: List[Dict[str, object]] = []
    seen: set[str] = set()
    for entry in MODEL_LIBRARY:
        key = str(entry.get("device")) if entry.get("device") else entry["slug"]
        if key in seen:
            continue
        seen.add(key)
        ordered.append(devices[key])
    return ordered


def _default_upload_root() -> str:
    """Derive the uploads root from DATA_DIR (#3)."""
    data_dir = current_app.config.get("DATA_DIR", "./data")
    return os.path.join(data_dir, "uploads")


@print_requests_bp.before_app_request
def _ensure_upload_folder() -> None:
    # #3: Upload roots are derived from DATA_DIR at request time. Operators
    # can override PRINT_REQUESTS_UPLOAD_FOLDER via .env or app.config; the
    # design-images sub-directory is always derived from the upload root at
    # request time (see _handle_design_image_upload), so no separate
    # PRINT_REQUESTS_IMAGE_UPLOAD_FOLDER config key is needed.
    current_app.config.setdefault("PRINT_REQUESTS_UPLOAD_FOLDER", _default_upload_root())


@print_requests_bp.route("/")
def list_requests() -> str:
    status = request.args.get("status")
    cards = _build_device_cards()
    return render_template(
        "print_requests_devices.html",
        status=status,
        devices=cards,
    )


@print_requests_bp.route("/library/<device_key>")
def device_library(device_key: str) -> str:
    device = _get_device_entry(device_key)
    if not device:
        abort(404)
    models = [
        _build_library_card(model)
        for model in MODEL_LIBRARY
        if str(model.get("device", "")).lower() == device["key"].lower()
    ]
    return render_template(
        "print_requests_library.html",
        status=request.args.get("status"),
        models=models,
        device=device,
    )


@print_requests_bp.route("/requests")
def request_queue() -> str:
    records = db.list_requests()
    normalized = [_normalize_record(record) for record in records]
    return render_template(
        "print_requests_queue.html",
        requests=[item for item in normalized if item.get("print_status") not in _CLOSED_STATUSES],
        status_options=_PRINT_STATUS_OPTIONS,
        status_message=request.args.get("status_message"),
    )


@print_requests_bp.route("/requests/history")
def request_history() -> str:
    records = db.list_requests()
    normalized = [_normalize_record(record) for record in records]
    return render_template(
        "print_requests_history.html",
        requests=[item for item in normalized if item.get("print_status") in _CLOSED_STATUSES],
    )


@print_requests_bp.route("/requests/<int:request_id>")
def request_detail(request_id: int) -> str:
    record = db.get_request(request_id)
    if not record:
        abort(404)
    return render_template(
        "print_request_detail.html",
        request_item=_normalize_record(record),
    )


@print_requests_bp.route("/requests/<int:request_id>/retry-jira", methods=["POST"])
def retry_jira_sync(request_id: int):
    """Re-dispatch the Jira ticket creation task for a request in error state."""
    record = db.get_request(request_id)
    if not record:
        abort(404)

    jira_task_status = record.get("jira_task_status")
    jira_sync_error = record.get("jira_sync_error")
    jira_ticket_key = record.get("jira_ticket_key")

    # Only retry if the record is actually in an error state or has never synced
    in_error = (
        jira_task_status == "error"
        or (jira_ticket_key is None and jira_sync_error)
    )
    if not in_error:
        return redirect(url_for("print_requests.request_detail", request_id=request_id))

    # Dispatch first, then write the task ID so the detail page can start polling
    # immediately on redirect (avoids a window where jira_task_id is NULL).
    celery_result = _create_jira_ticket_task.delay(request_id)
    db.update_task_status(request_id, status="pending", task_id=celery_result.id)
    return redirect(url_for("print_requests.request_detail", request_id=request_id))


def _resolve_upload_path(relative_path: str) -> str:
    """Resolve a relative upload path (#3) to an absolute filesystem path.

    Stored values are relative to DATA_DIR/uploads/ (e.g. "abc123/model.stl").
    Legacy absolute paths (written before Slice D-part1) are detected by the
    presence of os.sep at position 0 or a Windows drive letter, and returned
    unchanged so old records continue to work until the migration script is run.
    """
    if os.path.isabs(relative_path):
        # Legacy absolute path — still resolve as-is until migration is run.
        return relative_path
    upload_root = _get_upload_root()
    return os.path.join(upload_root, relative_path)


@print_requests_bp.route("/requests/<int:request_id>/files/<file_kind>")
def download_request_file(request_id: int, file_kind: str):
    """Serve a model or image file via object storage or local FS (#29).

    When the storage backend is S3, redirects to a presigned URL.
    When the backend is local (or the stored value is a legacy path), serves
    the file directly via send_file().
    """
    from flask import redirect as _redirect

    record = db.get_request(request_id)
    if not record:
        abort(404)
    if file_kind == "model":
        stored = record.get("uploaded_file_path")
    elif file_kind == "image":
        stored = record.get("uploaded_image_path")
    else:
        abort(404)

    if not stored:
        abort(404)

    # Backward-compat first: if a legacy local file exists at the resolved
    # upload path, serve it directly — regardless of the configured storage
    # backend. This protects rows written before the storage abstraction
    # landed from 404'ing after a switch to OBJECT_STORAGE_BACKEND=s3 (the
    # S3 bucket wouldn't have been populated for those rows).
    legacy_path = _resolve_upload_path(str(stored))
    if os.path.exists(legacy_path):
        return send_file(legacy_path, as_attachment=True)

    storage = current_app.config.get("OBJECT_STORAGE")
    if storage is not None:
        resolved = storage.url_for(str(stored))
        # Presigned URLs start with http(s):// — redirect to them.
        if resolved.startswith("http://") or resolved.startswith("https://"):
            return _redirect(resolved)
        if os.path.exists(resolved):
            return send_file(resolved, as_attachment=True)

    abort(404)


@print_requests_bp.route("/requests/<int:request_id>/preview/<file_kind>")
def preview_request_file(request_id: int, file_kind: str):
    """Preview a design image via object storage or local FS (#29).

    Backward-compat: serves any legacy local file first; redirects to a
    presigned URL only when no legacy file exists. See ``download_request_file``
    above for the rationale.
    """
    from flask import redirect as _redirect

    record = db.get_request(request_id)
    if not record:
        abort(404)
    if file_kind == "image":
        stored = record.get("uploaded_image_path")
    else:
        abort(404)

    if not stored:
        abort(404)

    # Backward-compat first — see download_request_file().
    legacy_path = _resolve_upload_path(str(stored))
    if os.path.exists(legacy_path):
        return send_file(legacy_path, as_attachment=False)

    storage = current_app.config.get("OBJECT_STORAGE")
    if storage is not None:
        resolved = storage.url_for(str(stored))
        if resolved.startswith("http://") or resolved.startswith("https://"):
            return _redirect(resolved)
        if os.path.exists(resolved):
            return send_file(resolved, as_attachment=False)

    abort(404)


@print_requests_bp.route("/requests/<int:request_id>/status", methods=["POST"])
def update_request_status(request_id: int):
    record = db.get_request(request_id)
    if not record:
        abort(404)

    status = (request.form.get("print_status") or "").strip()
    if status not in _PRINT_STATUS_OPTIONS:
        return redirect(url_for("print_requests.request_queue", status_message="Invalid status selection."))

    db.update_print_status(request_id, status)
    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
    _audit(
        actor=actor,
        action="print_requests.status_change",
        resource_type="print_request",
        resource_id=request_id,
        detail={"status": status},
    )
    status_message = "Status updated."

    if status in _CLOSED_STATUSES and record.get("jira_ticket_key"):
        transition_id = _get_jira_transition_id(status)
        if transition_id:
            # Dispatch Jira transition asynchronously (Wave 2, Issue #14).
            # Pass request_id so final-failure errors are written back to the DB.
            _transition_jira_ticket_task.delay(record["jira_ticket_key"], transition_id, request_id)
        else:
            db.update_jira_status(request_id, jira_ticket_key=record.get("jira_ticket_key"), jira_sync_error="Missing Jira transition id")
            status_message = "Status updated, but Jira transition is not configured."

    return redirect(url_for("print_requests.request_queue", status_message=status_message))


@print_requests_bp.route("/new", methods=["GET", "POST"])
def create_request() -> str:
    form_data = _default_form_data(request.args)
    errors: Dict[str, str] = {}

    if request.method == "POST":
        form_data = _extract_form_data(request)
        errors = _validate_form(form_data, request.files)

        if not errors:
            selected_details = _resolve_model_details(form_data)
            description = _compose_description(form_data, selected_details)
            upload_path = _handle_upload(form_data, request.files)
            image_path = _handle_design_image_upload(form_data, request.files)
            request_id = db.create_request(
                requester=form_data["requester"],
                team=form_data["team"],
                request_type=form_data["request_type"],
                selected_model_details=selected_details,
                quantity=int(form_data.get("quantity") or 1),
                due_date=form_data.get("due_date"),
                description=description,
                uploaded_file_path=upload_path,
                uploaded_image_path=image_path,
                print_status="Design",
            )
            # Dispatch Jira ticket creation asynchronously (Wave 2, Issue #14).
            # The form returns immediately; the Celery worker creates the ticket
            # in the background and updates jira_task_status / jira_ticket_key.
            if _jira_creation_enabled():
                _create_jira_ticket_task.delay(request_id)
            return redirect(url_for("print_requests.list_requests", status="created"))

    return render_template(
        "print_request_form.html",
        form=form_data,
        errors=errors,
        allowed_extensions=sorted(_ALLOWED_EXTENSIONS),
        allowed_image_extensions=sorted(_ALLOWED_IMAGE_EXTENSIONS),
        model_devices=_build_model_devices(),
    )


@print_requests_bp.context_processor
def inject_upload_note() -> Dict[str, object]:
    return {
        "print_requests_upload_dir": _get_upload_root(),
    }


def _build_library_card(model: Dict[str, object]) -> Dict[str, object]:
    preview_urls = _build_preview_urls(model.get("images", []))
    return {
        "slug": model["slug"],
        "name": model["name"],
        "description": model["description"],
        "category_label": model["category_label"],
        "device_label": model["device_label"],
        "variant_label": model["variant_label"],
        "preview_urls": preview_urls,
        "submit_url": url_for("print_requests.create_request", request_type="existing_model", model=model["slug"]),
    }


def _build_device_cards() -> List[Dict[str, object]]:
    cards: List[Dict[str, object]] = []
    for device in DEVICE_LIBRARY:
        device_models = [
            model
            for model in MODEL_LIBRARY
            if str(model.get("device", "")).lower() == str(device["key"]).lower()
        ]
        preview_urls = _build_preview_urls(device_models[0].get("images", [])) if device_models else []
        cards.append(
            {
                "key": device["key"],
                "name": device["name"],
                "description": device["description"],
                "tags": device.get("tags", []),
                "preview_urls": preview_urls,
                "model_count": len(device_models),
                "detail_url": url_for("print_requests.device_library", device_key=device["key"]),
            }
        )
    return cards


def _build_preview_urls(image_paths: List[str]) -> List[str]:
    return [url_for("print_requests.static", filename=path) for path in image_paths]


def _get_device_entry(device_key: str) -> Optional[Dict[str, object]]:
    for entry in DEVICE_LIBRARY:
        if str(entry.get("key", "")).lower() == device_key.lower():
            return entry
    return None


def _normalize_record(record: Dict[str, object]) -> Dict[str, object]:
    created_raw = str(record.get("created_at") or "")
    created_dt: Optional[datetime] = None
    try:
        created_dt = datetime.fromisoformat(created_raw)
    except ValueError:
        created_dt = None

    jira_ticket = record.get("jira_ticket_key")
    jira_error = record.get("jira_sync_error")
    jira_task_status = record.get("jira_task_status")
    if jira_ticket:
        jira_status = jira_ticket
    elif jira_error:
        jira_status = f"Jira error: {jira_error}"
    elif jira_task_status in ("pending", "processing"):
        jira_status = "Jira ticket pending"
    else:
        jira_status = "Not yet created"
    formatted = created_dt.strftime("%b %d, %Y %H:%M") if created_dt else created_raw

    details = record.get("selected_model_details") or {}
    detail_text = " / ".join(
        value
        for value in (
            details.get("category_label"),
            details.get("device_label"),
            details.get("variant_label"),
        )
        if value
    ) or "–"

    return {
        **record,
        "created_display": formatted,
        "jira_status": jira_status,
        "detail_text": detail_text,
    }


def _default_form_data(args) -> Dict[str, str]:
    base = {
        "requester": "",
        "team": "",
        "request_type": args.get("request_type", "existing_model") or "existing_model",
        "model_device": "",
        "model_variant": "",
        "model_choice": "",
        "category": args.get("category", ""),
        "device": args.get("device", ""),
        "variant": args.get("variant", ""),
        "description": "",
        "quantity": "1",
        "due_date": "",
    }

    slug = args.get("model")
    preselected = MODEL_INDEX.get(slug)
    if preselected:
        base["request_type"] = "existing_model"
        base["model_choice"] = preselected["slug"]
        base["model_variant"] = preselected["slug"]
        base["model_device"] = preselected.get("device", "")
        base["category"] = preselected.get("category", "")
        base["device"] = preselected.get("device", "")
        base["variant"] = preselected.get("variant", "")
    else:
        base["model_choice"] = args.get("model_choice", "")
        base["model_device"] = args.get("model_device", "")
        base["model_variant"] = args.get("model_variant", "")

    return base


def _extract_form_data(req) -> Dict[str, str]:
    return {
        "requester": (req.form.get("requester") or "").strip(),
        "team": (req.form.get("team") or "").strip(),
        "request_type": (req.form.get("request_type") or "").strip(),
        "model_device": (req.form.get("model_device") or "").strip(),
        "model_variant": (req.form.get("model_variant") or "").strip(),
        "model_choice": (req.form.get("model_variant") or req.form.get("model_choice") or "").strip(),
        "category": (req.form.get("category") or "").strip(),
        "device": (req.form.get("device") or "").strip(),
        "variant": (req.form.get("variant") or "").strip(),
        "description": (req.form.get("description") or "").strip(),
        "quantity": (req.form.get("quantity") or "").strip() or "1",
        "due_date": (req.form.get("due_date") or "").strip(),
    }


def _validate_form(form_data: Dict[str, str], files) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    request_type = form_data.get("request_type", "")

    if not form_data.get("requester"):
        errors["requester"] = "Requester name is required."

    if request_type == "existing_model":
        if not _resolve_model_details(form_data):
            errors["model_choice"] = "Select a valid model from the library."
    elif request_type == "upload_file":
        upload = files.get("upload")
        if not upload or not upload.filename:
            errors["upload"] = "Upload the model file to continue."
        elif not _is_allowed_file(upload.filename):
            errors["upload"] = "Allowed file types: .stl or .3mf"
        image_upload = files.get("design_image")
        if image_upload and image_upload.filename and not _is_allowed_image(image_upload.filename):
            errors["design_image"] = "Allowed image types: .png, .jpg, .jpeg"
    elif request_type == "new_design":
        if not form_data.get("description"):
            errors["description"] = "Provide details for the new design."
        upload = files.get("upload")
        if upload and upload.filename and not _is_allowed_file(upload.filename):
            errors["upload"] = "Allowed file types: .stl or .3mf"
        image_upload = files.get("design_image")
        if image_upload and image_upload.filename and not _is_allowed_image(image_upload.filename):
            errors["design_image"] = "Allowed image types: .png, .jpg, .jpeg"
    else:
        errors["request_type"] = "Unknown request type."

    try:
        quantity = int(form_data.get("quantity") or 0)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        errors["quantity"] = "Enter a whole number greater than zero."

    due_date = form_data.get("due_date")
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            errors["due_date"] = "Use the date picker to choose a valid date."

    return errors


def _resolve_model_details(form_data: Dict[str, str]) -> Optional[Dict[str, str]]:
    slug = form_data.get("model_choice") or form_data.get("model_variant")
    if slug:
        entry = MODEL_INDEX.get(slug)
        if not entry:
            return None
        return {
            "category": entry.get("category"),
            "category_label": entry.get("category_label"),
            "category_image": entry.get("category_image"),
            "device": entry.get("device"),
            "device_label": entry.get("device_label"),
            "device_image": entry.get("device_image"),
            "variant": entry.get("variant"),
            "variant_label": entry.get("variant_label"),
            "variant_image": entry.get("variant_image"),
            "model_name": entry.get("name"),
            "slug": slug,
        }

    category_key = form_data.get("category")
    device_key = form_data.get("device")
    variant_key = form_data.get("variant")

    if not category_key or not device_key or not variant_key:
        return None

    category = MODEL_HIERARCHY.get(category_key)
    if not category:
        return None
    device = category["devices"].get(device_key)
    if not device:
        return None
    variant = device["variants"].get(variant_key)
    if not variant:
        return None

    slug = variant.get("slug")
    library_entry = MODEL_INDEX.get(slug) if slug else None

    return {
        "category": category_key,
        "category_label": category["label"],
        "category_image": category.get("image"),
        "device": device_key,
        "device_label": device["label"],
        "device_image": device.get("image"),
        "variant": variant_key,
        "variant_label": variant["label"],
        "variant_image": variant.get("image"),
        "model_name": variant.get("name") or (library_entry.get("name") if library_entry else variant["label"]),
        "slug": slug,
    }


def _compose_description(form_data: Dict[str, str], selected_details: Optional[Dict[str, str]]) -> str:
    request_type = form_data.get("request_type", "")
    notes = form_data.get("description", "")
    quantity = form_data.get("quantity") or "1"
    due_date = form_data.get("due_date")

    sections: List[str] = []

    if request_type == "existing_model" and selected_details:
        sections.append(f"Existing model requested: {selected_details.get('model_name', 'Unnamed model')}")
        sections.append(
            "Selections:\n"
            f"- Category: {selected_details.get('category_label')}\n"
            f"- Device: {selected_details.get('device_label')}\n"
            f"- Variant: {selected_details.get('variant_label')}"
        )
    elif request_type == "upload_file":
        sections.append("Requester supplied a model file for printing.")
    elif request_type == "new_design":
        sections.append("New design request submitted by the lab team.")

    quantity_section = _compose_quantity_section(quantity)
    if quantity_section:
        sections.append(quantity_section)

    due_section = _compose_due_date_section(due_date)
    if due_section:
        sections.append(due_section)

    if notes:
        sections.append(f"Requester notes:\n{notes}")

    return "\n\n".join(section for section in sections if section)


def _compose_quantity_section(quantity: Optional[str]) -> Optional[str]:
    try:
        qty = int(quantity or 0)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None
    return f"Quantity requested: {qty}"


def _compose_due_date_section(due_date: Optional[str]) -> Optional[str]:
    if not due_date:
        return None
    return f"Requested due date: {due_date}"


def _create_jira_ticket(request_id: int) -> None:
    record = db.get_request(request_id)
    if not record:
        return

    if not _jira_creation_enabled():
        return

    if not _jira_is_configured():
        db.update_jira_status(request_id, jira_ticket_key=None, jira_sync_error="Jira is not configured")
        return

    summary = _build_jira_summary(record)
    description = _build_jira_description(record)
    attachments = [path for path in (record.get("uploaded_file_path"), record.get("uploaded_image_path")) if path]
    deadline = record.get("due_date") or _compute_default_deadline(record.get("created_at"))

    # Read Jira defaults from config — wired to env vars via config.py (Slice A, Issue #6)
    assignee = current_app.config.get("PRINT_REQUESTS_DEFAULT_ASSIGNEE") or _DEFAULT_JIRA_ASSIGNEE
    priority = current_app.config.get("PRINT_REQUESTS_DEFAULT_PRIORITY") or _DEFAULT_JIRA_PRIORITY
    request_type = current_app.config.get("PRINT_REQUESTS_DEFAULT_REQUEST_TYPE") or _DEFAULT_JIRA_REQUEST_TYPE
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
        db.update_jira_status(request_id, jira_ticket_key=None, jira_sync_error=str(exc))
        return

    db.update_jira_status(request_id, jira_ticket_key=issue_key, jira_sync_error=None)
    actor = (session.get("user_identity") or {}).get("email", "<unknown>")
    _audit(
        actor=actor,
        action="print_requests.jira_sync",
        resource_type="print_request",
        resource_id=request_id,
        detail={"jira_ticket_key": issue_key},
    )


def _build_jira_summary(record: Dict[str, object]) -> str:
    base = str(record.get("description") or record.get("request_type") or "3D Print Request")
    first_line = base.splitlines()[0].strip() if base else "3D Print Request"
    if len(first_line) > 80:
        first_line = f"{first_line[:77]}..."
    return f"3D Print Request: {first_line}" if not first_line.lower().startswith("3d print request") else first_line


def _build_jira_description(record: Dict[str, object]) -> str:
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


def _compute_default_deadline(created_at: Optional[object]) -> str:
    if isinstance(created_at, str) and created_at:
        try:
            created_dt = datetime.fromisoformat(created_at)
            base_date = created_dt.date()
        except ValueError:
            base_date = date.today()
    else:
        base_date = date.today()
    return (base_date + timedelta(days=_DEFAULT_JIRA_DEADLINE_DAYS)).isoformat()


def _handle_upload(form_data: Dict[str, str], files) -> Optional[str]:
    """Save an uploaded model file via object storage and return its key (#29).

    When OBJECT_STORAGE_BACKEND=local the key is a filename under DATA_DIR/uploads/
    (no path separator), identical in semantics to the old relative path.
    When OBJECT_STORAGE_BACKEND=s3 the key is written to the configured bucket.

    In both cases only the *key* is stored in the DB; serving routes call
    storage.url_for(key) to resolve it.  Backward-compat: old DB rows that
    contain a legacy relative path with os.sep are handled by url_for().
    """
    upload = files.get("upload")
    if not upload or not upload.filename:
        return None
    if not _is_allowed_file(upload.filename):
        return None

    filename = secure_filename(upload.filename)
    key = f"{uuid.uuid4().hex}_{filename}"
    storage = current_app.config.get("OBJECT_STORAGE")
    if storage is not None:
        # Stream from the upload's underlying file object rather than calling
        # upload.read() — large STL/3MF files would otherwise buffer entirely
        # in memory (OOM risk under concurrent uploads).
        storage.put_stream(key, upload.stream, content_type=upload.mimetype)
    else:
        # Fallback: write directly to local FS (defensive; storage should always
        # be set after _init_storage runs).
        root = _get_upload_root()
        os.makedirs(root, exist_ok=True)
        upload.save(os.path.join(root, key))
    return key


def _handle_design_image_upload(form_data: Dict[str, str], files) -> Optional[str]:
    """Save an uploaded design image via object storage and return its key (#29).

    Design images are stored under the ``design_images/`` prefix so they are
    distinguishable from model files in the object store / local tree.
    """
    if form_data.get("request_type") not in {"new_design", "upload_file"}:
        return None
    upload = files.get("design_image")
    if not upload or not upload.filename:
        return None
    if not _is_allowed_image(upload.filename):
        return None

    filename = secure_filename(upload.filename)
    # Prefix with "design_images/" to namespace images from model files.
    key = f"design_images/{uuid.uuid4().hex}_{filename}"
    storage = current_app.config.get("OBJECT_STORAGE")
    if storage is not None:
        # Stream (see _handle_upload above for rationale).
        storage.put_stream(key, upload.stream, content_type=upload.mimetype)
    else:
        root = _get_upload_root()
        image_dir = os.path.join(root, "design_images")
        os.makedirs(image_dir, exist_ok=True)
        upload.save(os.path.join(image_dir, os.path.basename(key)))
    return key


def _is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS


def _is_allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in _ALLOWED_IMAGE_EXTENSIONS


def _get_upload_root() -> str:
    """Return the absolute upload root directory for this tool (#3)."""
    return current_app.config.get("PRINT_REQUESTS_UPLOAD_FOLDER") or _default_upload_root()


def _get_jira_transition_id(status: str) -> Optional[str]:
    if status == "Cancelled":
        return current_app.config.get("PRINT_REQUESTS_JIRA_CANCEL_TRANSITION_ID")
    if status == "Closed":
        return current_app.config.get("PRINT_REQUESTS_JIRA_CLOSE_TRANSITION_ID")
    return None


def _jira_is_configured() -> bool:
    return bool(os.getenv("JIRA_URL") and os.getenv("JIRA_PAT"))


def _jira_creation_enabled() -> bool:
    config_value = current_app.config.get("PRINT_REQUESTS_CREATE_JIRA")
    if config_value is not None:
        return bool(config_value)
    env_value = os.getenv("PRINT_REQUESTS_CREATE_JIRA", "true").strip().lower()
    return env_value not in {"0", "false", "no"}
