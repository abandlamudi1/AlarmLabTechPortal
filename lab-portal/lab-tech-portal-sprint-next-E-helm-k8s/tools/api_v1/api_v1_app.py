"""JSON API blueprint for the Lab Tech Portal.

Slice D, Issue #35.
Registered by app.py at /api/v1/ with CSRF exemption.

API endpoints return JSON.  Unauthenticated requests receive 401 JSON
(not a 302 redirect) so API clients are not confused by HTML login pages.
Note: blueprint-level HTTP exceptions raised by ``requires_role`` (403) or
Flask's own routing (404, 405) are *not* intercepted by this blueprint and
will return the default Flask response format (HTML in production, JSON in
test mode depending on app config).

PR 1 endpoints:
  GET  /api/v1/inventory/items        — list inventory items
  POST /api/v1/inventory/items        — create inventory item
  GET  /api/v1/checkout/equipment     — list checkout equipment
  POST /api/v1/checkout/equipment/<id>/checkout — check out item
  GET  /api/v1/audit-log              — audit log (migrated from app.py)

PR 2 endpoints:
  GET  /api/v1/print-requests         — list print requests
  POST /api/v1/print-requests         — create print request
  GET  /api/v1/systems                — list systems
  GET  /api/v1/rf-chambers            — list RF chambers
"""
from __future__ import annotations

import logging
import os
import re

import qrcode

from flask import Blueprint, current_app, jsonify, request, session

from services.audit_log import get_recent_events as _audit_get_events
from services.rbac import requires_role as _requires_role
import tools.inventory.db as _inventory_db
import tools.checkout.db as _checkout_db
import tools.print_requests.db as _print_requests_db
import tools.system_locator.db as _systems_db
import tools.rf_chamber.db as _rf_db

api_v1_bp = Blueprint("api_v1", __name__)


@api_v1_bp.before_request
def _require_auth():
    """Return 401 JSON for unauthenticated API callers.

    Skips the check when LOGIN_DISABLED is True (dev/test mode) so tests
    do not need to set up a session.  When auth is active, the presence of
    ``session['user_identity']`` (set by app.py's auth_callback) is the
    canonical signal that the user is logged in.
    """
    if current_app.config.get("LOGIN_DISABLED"):
        return None
    if not session.get("user_identity"):
        return jsonify({"error": "Unauthorized"}), 401
    return None


# ---------------------------------------------------------------------------
# Audit log (migrated from app.py, URL preserved)
# ---------------------------------------------------------------------------


@api_v1_bp.route("/audit-log")
@_requires_role("admin")
def audit_log():
    """Return recent audit events.  Admin-only (403 on role mismatch).

    Query params:
      limit  — max rows to return (default 50, capped at 200)
      offset — row offset for pagination (default 0)

    Response::

        {"events": [...], "count": N}
    ---
    tags:
      - audit-log
    parameters:
      - name: limit
        in: query
        type: integer
        default: 50
        description: Max rows to return (capped at 200)
      - name: offset
        in: query
        type: integer
        default: 0
        description: Row offset for pagination
    responses:
      200:
        description: List of recent audit events
        schema:
          type: object
          properties:
            events:
              type: array
              items:
                type: object
            count:
              type: integer
      400:
        description: Invalid limit or offset parameter
      401:
        description: Unauthorized
      403:
        description: Admin role required
    """
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "limit and offset must be integers"}), 400
    if limit < 1:
        return jsonify({"error": "limit must be a positive integer"}), 400
    if offset < 0:
        return jsonify({"error": "offset must be non-negative"}), 400

    events = _audit_get_events(limit=limit, offset=offset)
    return jsonify({"events": events, "count": len(events)})


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


@api_v1_bp.get("/inventory/items")
def list_inventory_items():
    """GET /api/v1/inventory/items — return all inventory items as JSON.

    Response::

        {"items": [...], "count": N}
    ---
    tags:
      - inventory
    responses:
      200:
        description: List of all inventory items
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  description:
                    type: string
                  quantity:
                    type: integer
                  min_stock:
                    type: integer
            count:
              type: integer
      401:
        description: Unauthorized
    """
    items = _inventory_db.get_items()
    return jsonify({"items": items, "count": len(items)})


@api_v1_bp.post("/inventory/items")
def create_inventory_item():
    """POST /api/v1/inventory/items — create a new inventory item.

    Request body (JSON):
      name        — string, required
      description — string, optional (default empty string, matching HTML form
                    behaviour where description may be omitted)
      quantity    — integer, required (must be >= 0)
      min_stock   — integer, required (must be >= 0)

    Response on success (201)::

        {"id": <new_id>, "name": ..., "description": ...,
         "quantity": ..., "min_stock": ...}

    Response on validation failure (400)::

        {"error": "field X is required"}
    ---
    tags:
      - inventory
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - quantity
            - min_stock
          properties:
            name:
              type: string
              description: Item name (required)
            description:
              type: string
              description: Optional description
            quantity:
              type: integer
              minimum: 0
              description: Current quantity
            min_stock:
              type: integer
              minimum: 0
              description: Minimum stock threshold
    responses:
      201:
        description: Item created successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            description:
              type: string
            quantity:
              type: integer
            min_stock:
              type: integer
      400:
        description: Validation error
      401:
        description: Unauthorized
    """
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    if not body.get("name"):
        return jsonify({"error": "name is required"}), 400

    for field in ("quantity", "min_stock"):
        if body.get(field) is None:
            return jsonify({"error": f"{field} is required"}), 400
        try:
            int(body[field])
        except (TypeError, ValueError):
            return jsonify({"error": f"{field} must be an integer"}), 400

    name = str(body["name"]).strip()
    # description is optional — matches HTML form which allows blank descriptions
    description = str(body.get("description") or "").strip()
    quantity = int(body["quantity"])
    min_stock = int(body["min_stock"])

    if not name:
        return jsonify({"error": "name is required"}), 400

    # Fix: reject negative values — HTML form enforces min=0 via browser;
    # the API must enforce the same constraint server-side.
    if quantity < 0:
        return jsonify({"error": "quantity must be >= 0"}), 400
    if min_stock < 0:
        return jsonify({"error": "min_stock must be >= 0"}), 400

    new_id = _inventory_db.add_item(
        name=name,
        description=description,
        quantity=quantity,
        min_stock=min_stock,
    )

    # Generate QR PNG — mirrors the HTML /inventory/add_item flow (#91, #29).
    # Routed through ObjectStorage abstraction so QR PNGs go to object storage
    # when OBJECT_STORAGE_BACKEND=s3, or local FS when backend=local.
    # Failure is non-fatal: item is already persisted; log a warning and continue.
    try:
        from tools.inventory.inventory_app import _generate_qr_png
        qr_key = f"qr_{new_id}.png"
        storage = current_app.config.get("OBJECT_STORAGE")
        if storage is not None:
            png_bytes = _generate_qr_png(new_id)
            storage.put(qr_key, png_bytes, content_type="image/png")
        else:
            data_dir = current_app.config.get("DATA_DIR", "./data")
            qr_dir = os.path.join(data_dir, "generated", "inventory")
            os.makedirs(qr_dir, exist_ok=True)
            qrcode.make(str(new_id)).save(os.path.join(qr_dir, qr_key))
        _inventory_db.set_qr_code(new_id, qr_key)
    except Exception:
        logging.getLogger(__name__).warning(
            "QR generation failed for item %s; item created without QR code.",
            new_id,
            exc_info=True,
        )

    return (
        jsonify(
            {
                "id": new_id,
                "name": name,
                "description": description,
                "quantity": quantity,
                "min_stock": min_stock,
            }
        ),
        201,
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row (or dict-like) checkout row to a plain dict."""
    return {
        "id": row["id"],
        "name": row["name"],
        "checked_out_by": row["checked_out_by"],
        "checked_out_at": row["checked_out_at"],
        "return_date": row["return_date"],
        "jira_link": row["jira_link"],
    }


@api_v1_bp.get("/checkout/equipment")
def list_checkout_equipment():
    """GET /api/v1/checkout/equipment — return all checkout equipment as JSON.

    Response::

        {"equipment": [...], "count": N}
    ---
    tags:
      - checkout
    responses:
      200:
        description: List of all checkout equipment
        schema:
          type: object
          properties:
            equipment:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  checked_out_by:
                    type: string
                  checked_out_at:
                    type: string
                  return_date:
                    type: string
                  jira_link:
                    type: string
            count:
              type: integer
      401:
        description: Unauthorized
    """
    rows = _checkout_db.list_equipment()
    equipment = [_row_to_dict(r) for r in rows]
    return jsonify({"equipment": equipment, "count": len(equipment)})


@api_v1_bp.post("/checkout/equipment/<int:item_id>/checkout")
def checkout_equipment(item_id: int):
    """POST /api/v1/checkout/equipment/<id>/checkout — check out an item.

    Request body (JSON):
      user_name   — string, required
      return_date — string (YYYY-MM-DD), required
      jira_link   — string, optional

    Response on success (200)::

        {"id": <item_id>, "user_name": ..., "return_date": ...}

    Response on validation failure (400)::

        {"error": "field X is required"}

    Response when item not found or already checked out (409)::

        {"error": "Item not available for checkout"}
    ---
    tags:
      - checkout
    consumes:
      - application/json
    parameters:
      - name: item_id
        in: path
        type: integer
        required: true
        description: Equipment item ID to check out
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - user_name
            - return_date
          properties:
            user_name:
              type: string
              description: Name of the person checking out the item
            return_date:
              type: string
              format: date
              description: Expected return date (YYYY-MM-DD)
            jira_link:
              type: string
              description: Optional JIRA ticket link
    responses:
      200:
        description: Item checked out successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            user_name:
              type: string
            return_date:
              type: string
      400:
        description: Validation error (missing fields or invalid date format)
      401:
        description: Unauthorized
      409:
        description: Item not available for checkout
    """
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    for field in ("user_name", "return_date"):
        if not body.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    user_name = str(body["user_name"]).strip()
    return_date = str(body["return_date"]).strip()
    jira_link = str(body.get("jira_link") or "").strip()

    if not user_name:
        return jsonify({"error": "user_name is required"}), 400
    if not return_date:
        return jsonify({"error": "return_date is required"}), 400

    # Fix: validate date format in the API layer so bad input returns 400
    # rather than 409.  checkout_db.checkout_item() returns False for both
    # invalid-date and true-conflict cases, making 409 vs 400 indistinguishable
    # without a pre-check here.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", return_date):
        return jsonify({"error": "return_date must be in YYYY-MM-DD format"}), 400

    success = _checkout_db.checkout_item(item_id, user_name, return_date, jira_link)
    if not success:
        return jsonify({"error": "Item not available for checkout"}), 409

    return jsonify({"id": item_id, "user_name": user_name, "return_date": return_date})


# ---------------------------------------------------------------------------
# Print Requests
# ---------------------------------------------------------------------------


@api_v1_bp.get("/print-requests")
def list_print_requests():
    """GET /api/v1/print-requests — return all print requests as JSON.

    Response::

        {"requests": [...], "count": N}
    ---
    tags:
      - print-requests
    responses:
      200:
        description: List of all print requests
        schema:
          type: object
          properties:
            requests:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  requester:
                    type: string
                  request_type:
                    type: string
                  quantity:
                    type: integer
                  team:
                    type: string
                  description:
                    type: string
                  due_date:
                    type: string
            count:
              type: integer
      401:
        description: Unauthorized
    """
    requests_list = _print_requests_db.list_requests()
    return jsonify({"requests": requests_list, "count": len(requests_list)})


@api_v1_bp.post("/print-requests")
def create_print_request():
    """POST /api/v1/print-requests — create a new 3D print request.

    Request body (JSON):
      requester    — string, required
      request_type — string, required
      quantity     — integer, optional (default 1)
      team         — string, optional
      description  — string, optional
      due_date     — string (YYYY-MM-DD), optional

    Response on success (201)::

        {"id": <new_id>, "requester": ..., "request_type": ...}

    Response on validation failure (400)::

        {"error": "field X is required"}
    ---
    tags:
      - print-requests
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - requester
            - request_type
          properties:
            requester:
              type: string
              description: Name of the requester
            request_type:
              type: string
              description: Type of print request
            quantity:
              type: integer
              minimum: 1
              default: 1
              description: Number of items to print
            team:
              type: string
              description: Optional team name
            description:
              type: string
              description: Optional description
            due_date:
              type: string
              format: date
              description: Optional due date (YYYY-MM-DD)
    responses:
      201:
        description: Print request created successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            requester:
              type: string
            request_type:
              type: string
      400:
        description: Validation error
      401:
        description: Unauthorized
    """
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    for field in ("requester", "request_type"):
        if not body.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    requester = str(body["requester"]).strip()
    request_type = str(body["request_type"]).strip()

    if not requester:
        return jsonify({"error": "requester is required"}), 400
    if not request_type:
        return jsonify({"error": "request_type is required"}), 400

    quantity = body.get("quantity", 1)
    try:
        quantity = max(int(quantity), 1)
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be an integer"}), 400

    try:
        new_id = _print_requests_db.create_request(
            requester=requester,
            team=str(body.get("team") or "").strip(),
            request_type=request_type,
            selected_model_details=None,
            quantity=quantity,
            due_date=str(body.get("due_date") or "").strip() or None,
            description=str(body.get("description") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"id": new_id, "requester": requester, "request_type": request_type}), 201


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------


@api_v1_bp.get("/systems")
def list_systems():
    """GET /api/v1/systems — return all systems as JSON.

    Response::

        {"systems": [...], "count": N}
    ---
    tags:
      - systems
    responses:
      200:
        description: List of all systems
        schema:
          type: object
          properties:
            systems:
              type: array
              items:
                type: object
            count:
              type: integer
      401:
        description: Unauthorized
    """
    systems = _systems_db.list_systems()
    return jsonify({"systems": systems, "count": len(systems)})


# ---------------------------------------------------------------------------
# RF Chambers
# ---------------------------------------------------------------------------


@api_v1_bp.get("/rf-chambers")
def list_rf_chambers():
    """GET /api/v1/rf-chambers — return all RF chambers as JSON.

    Response::

        {"chambers": [...], "count": N}
    ---
    tags:
      - rf-chambers
    responses:
      200:
        description: List of all RF chambers
        schema:
          type: object
          properties:
            chambers:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  barcode:
                    type: string
                  size:
                    type: string
                  ports:
                    type: string
                  purpose:
                    type: string
                  location:
                    type: string
                  owner:
                    type: string
            count:
              type: integer
      401:
        description: Unauthorized
    """
    chambers = _rf_db.list_chambers()
    return jsonify({"chambers": chambers, "count": len(chambers)})


# ---------------------------------------------------------------------------
# Task Status  (Slice C, Issue #16)
# ---------------------------------------------------------------------------


@api_v1_bp.get("/tasks/<task_id>/status")
def task_status(task_id: str):
    """GET /api/v1/tasks/<task_id>/status — return current Celery task state.

    Queries the Celery result backend directly using the task UUID so the UI
    can poll for pending/processing/success/error transitions without coupling
    to the print-requests table.

    Response::

        {
          "task_id": "<uuid>",
          "state":   "PENDING | STARTED | SUCCESS | FAILURE | RETRY",
          "result":  {...} | null,
          "error":   "<exception string>" | null
        }

    ``result`` is populated only on SUCCESS; ``error`` only on FAILURE.
    The lazy import avoids a circular-import because app.py imports this
    blueprint *before* the module-level ``celery = make_celery(app)`` line.
    """
    from app import celery as _celery  # lazy — avoids circular import at module level

    result = _celery.AsyncResult(task_id)
    return jsonify({
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
        "error": str(result.result) if result.failed() else None,
    })
