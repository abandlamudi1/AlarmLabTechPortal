"""Tests for the api_v1 JSON API blueprint (Slice D, Issue #35).

PR 1 coverage:
  - Blueprint is registered at /api/v1/
  - GET  /api/v1/inventory/items
  - POST /api/v1/inventory/items (valid and invalid payloads)
  - GET  /api/v1/checkout/equipment
  - POST /api/v1/checkout/equipment/<id>/checkout (valid and invalid)

PR 2 coverage:
  - GET  /api/v1/print-requests
  - POST /api/v1/print-requests (valid and invalid payloads)
  - GET  /api/v1/systems
  - GET  /api/v1/rf-chambers
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client, url, payload):
    return client.post(url, json=payload, content_type="application/json")


# ---------------------------------------------------------------------------
# Blueprint registration smoke test
# ---------------------------------------------------------------------------


def test_api_v1_inventory_route_exists(client):
    """The /api/v1/inventory/items route must respond (not 404)."""
    resp = client.get("/api/v1/inventory/items")
    assert resp.status_code != 404


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/items
# ---------------------------------------------------------------------------


def test_list_inventory_items_returns_200(client):
    resp = client.get("/api/v1/inventory/items")
    assert resp.status_code == 200


def test_list_inventory_items_returns_json(client):
    resp = client.get("/api/v1/inventory/items")
    data = resp.get_json()
    assert data is not None
    assert "items" in data
    assert "count" in data


def test_list_inventory_items_count_matches(client):
    resp = client.get("/api/v1/inventory/items")
    data = resp.get_json()
    assert data["count"] == len(data["items"])


def test_list_inventory_items_contains_seeded_item(client):
    """conftest seeds one item (Spectrum Analyzer); it must appear in the list."""
    resp = client.get("/api/v1/inventory/items")
    data = resp.get_json()
    names = [item["name"] for item in data["items"]]
    assert "Spectrum Analyzer" in names


# ---------------------------------------------------------------------------
# POST /api/v1/inventory/items — valid input
# ---------------------------------------------------------------------------


def test_create_inventory_item_returns_201(client):
    payload = {
        "name": "Logic Analyzer",
        "description": "Saleae 8-channel",
        "quantity": 2,
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 201


def test_create_inventory_item_response_has_id(client):
    payload = {
        "name": "Signal Generator",
        "description": "Keysight 33600A",
        "quantity": 1,
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    data = resp.get_json()
    assert "id" in data
    assert isinstance(data["id"], int)


def test_create_inventory_item_appears_in_list(client):
    payload = {
        "name": "Network Analyzer",
        "description": "Keysight E5063A",
        "quantity": 1,
        "min_stock": 1,
    }
    _post_json(client, "/api/v1/inventory/items", payload)
    resp = client.get("/api/v1/inventory/items")
    data = resp.get_json()
    names = [item["name"] for item in data["items"]]
    assert "Network Analyzer" in names


# ---------------------------------------------------------------------------
# POST /api/v1/inventory/items — validation failures
# ---------------------------------------------------------------------------


def test_create_inventory_item_missing_name_returns_400(client):
    payload = {"description": "No name", "quantity": 1, "min_stock": 1}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_create_inventory_item_missing_description_defaults_to_empty(client):
    """description is optional — omitting it should succeed (matches HTML form behaviour)."""
    payload = {"name": "Widget No Description", "quantity": 1, "min_stock": 1}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["description"] == ""


def test_create_inventory_item_negative_quantity_returns_400(client):
    payload = {"name": "Widget", "description": "desc", "quantity": -1, "min_stock": 1}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_create_inventory_item_negative_min_stock_returns_400(client):
    payload = {"name": "Widget", "description": "desc", "quantity": 1, "min_stock": -5}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_create_inventory_item_missing_quantity_returns_400(client):
    payload = {"name": "Widget", "description": "Desc", "min_stock": 1}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400


def test_create_inventory_item_missing_min_stock_returns_400(client):
    payload = {"name": "Widget", "description": "Desc", "quantity": 1}
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400


def test_create_inventory_item_non_integer_quantity_returns_400(client):
    payload = {
        "name": "Widget",
        "description": "Desc",
        "quantity": "many",
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 400


def test_create_inventory_item_no_body_returns_400(client):
    resp = client.post("/api/v1/inventory/items", data="not json",
                       content_type="text/plain")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/v1/checkout/equipment
# ---------------------------------------------------------------------------


def test_list_checkout_equipment_returns_200(client):
    resp = client.get("/api/v1/checkout/equipment")
    assert resp.status_code == 200


def test_list_checkout_equipment_returns_json(client):
    resp = client.get("/api/v1/checkout/equipment")
    data = resp.get_json()
    assert data is not None
    assert "equipment" in data
    assert "count" in data


def test_list_checkout_equipment_count_matches(client):
    resp = client.get("/api/v1/checkout/equipment")
    data = resp.get_json()
    assert data["count"] == len(data["equipment"])


def test_list_checkout_equipment_has_expected_fields(client):
    resp = client.get("/api/v1/checkout/equipment")
    data = resp.get_json()
    if data["equipment"]:
        item = data["equipment"][0]
        for field in ("id", "name", "checked_out_by", "checked_out_at", "return_date"):
            assert field in item


# ---------------------------------------------------------------------------
# POST /api/v1/checkout/equipment/<id>/checkout — valid input
# ---------------------------------------------------------------------------


def _get_available_item_id(client) -> int:
    """Return the id of an available (not checked out) equipment item."""
    resp = client.get("/api/v1/checkout/equipment")
    data = resp.get_json()
    for item in data["equipment"]:
        if not item["checked_out_by"]:
            return item["id"]
    raise RuntimeError("No available equipment item found in test DB")


def test_checkout_equipment_returns_200(client):
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Alice", "return_date": "2026-06-01"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 200


def test_checkout_equipment_response_has_expected_fields(client):
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Bob", "return_date": "2026-06-15"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    data = resp.get_json()
    assert data["id"] == item_id
    assert data["user_name"] == "Bob"
    assert data["return_date"] == "2026-06-15"


def test_checkout_equipment_already_checked_out_returns_409(client):
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Charlie", "return_date": "2026-06-01"}
    _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    # Second checkout attempt on the same item must fail.
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/checkout/equipment/<id>/checkout — validation failures
# ---------------------------------------------------------------------------


def test_checkout_equipment_missing_user_name_returns_400(client):
    item_id = _get_available_item_id(client)
    payload = {"return_date": "2026-06-01"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_checkout_equipment_missing_return_date_returns_400(client):
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Diana"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 400


def test_checkout_equipment_no_body_returns_400(client):
    item_id = _get_available_item_id(client)
    resp = client.post(f"/api/v1/checkout/equipment/{item_id}/checkout",
                       data="not json", content_type="text/plain")
    assert resp.status_code == 400


def test_checkout_equipment_invalid_return_date_format_returns_400(client):
    """Invalid date format must return 400, not 409 (conflict)."""
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Alice", "return_date": "01/06/2026"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_checkout_equipment_nonsense_return_date_returns_400(client):
    """Freeform text in return_date must return 400, not 409."""
    item_id = _get_available_item_id(client)
    payload = {"user_name": "Bob", "return_date": "next-friday"}
    resp = _post_json(client, f"/api/v1/checkout/equipment/{item_id}/checkout", payload)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Unauthenticated access returns 401 JSON (not 302 redirect)
# ---------------------------------------------------------------------------


def test_api_v1_returns_401_json_when_not_authenticated(app, client):
    """When LOGIN_DISABLED=False and no session, API must return 401 JSON."""
    app.config["LOGIN_DISABLED"] = False
    try:
        resp = client.get("/api/v1/inventory/items")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data is not None
        assert "error" in data
    finally:
        app.config["LOGIN_DISABLED"] = True


# ---------------------------------------------------------------------------
# GET /api/v1/print-requests
# ---------------------------------------------------------------------------


def test_list_print_requests_returns_200(client):
    resp = client.get("/api/v1/print-requests")
    assert resp.status_code == 200


def test_list_print_requests_returns_json(client):
    resp = client.get("/api/v1/print-requests")
    data = resp.get_json()
    assert data is not None
    assert "requests" in data
    assert "count" in data


def test_list_print_requests_count_matches(client):
    resp = client.get("/api/v1/print-requests")
    data = resp.get_json()
    assert data["count"] == len(data["requests"])


# ---------------------------------------------------------------------------
# POST /api/v1/print-requests — valid input
# ---------------------------------------------------------------------------


def test_create_print_request_returns_201(client):
    payload = {"requester": "Alice", "request_type": "Custom Part"}
    resp = _post_json(client, "/api/v1/print-requests", payload)
    assert resp.status_code == 201


def test_create_print_request_response_has_id(client):
    payload = {"requester": "Bob", "request_type": "Bracket"}
    resp = _post_json(client, "/api/v1/print-requests", payload)
    data = resp.get_json()
    assert "id" in data
    assert isinstance(data["id"], int)


def test_create_print_request_appears_in_list(client):
    payload = {"requester": "Charlie", "request_type": "Enclosure"}
    _post_json(client, "/api/v1/print-requests", payload)
    resp = client.get("/api/v1/print-requests")
    data = resp.get_json()
    requesters = [r["requester"] for r in data["requests"]]
    assert "Charlie" in requesters


def test_create_print_request_with_optional_fields(client):
    payload = {
        "requester": "Diana",
        "request_type": "Mount",
        "quantity": 3,
        "team": "QE Infra",
        "description": "Wall mount for oscilloscope",
    }
    resp = _post_json(client, "/api/v1/print-requests", payload)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# POST /api/v1/print-requests — validation failures
# ---------------------------------------------------------------------------


def test_create_print_request_missing_requester_returns_400(client):
    payload = {"request_type": "Part"}
    resp = _post_json(client, "/api/v1/print-requests", payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_create_print_request_missing_request_type_returns_400(client):
    payload = {"requester": "Eve"}
    resp = _post_json(client, "/api/v1/print-requests", payload)
    assert resp.status_code == 400


def test_create_print_request_invalid_quantity_returns_400(client):
    payload = {"requester": "Frank", "request_type": "Part", "quantity": "lots"}
    resp = _post_json(client, "/api/v1/print-requests", payload)
    assert resp.status_code == 400


def test_create_print_request_no_body_returns_400(client):
    resp = client.post("/api/v1/print-requests", data="not json",
                       content_type="text/plain")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/v1/systems
# ---------------------------------------------------------------------------


def test_list_systems_returns_200(client):
    resp = client.get("/api/v1/systems")
    assert resp.status_code == 200


def test_list_systems_returns_json(client):
    resp = client.get("/api/v1/systems")
    data = resp.get_json()
    assert data is not None
    assert "systems" in data
    assert "count" in data


def test_list_systems_count_matches(client):
    resp = client.get("/api/v1/systems")
    data = resp.get_json()
    assert data["count"] == len(data["systems"])


def test_list_systems_starts_empty(client):
    """conftest seeds an empty systems DB; list must be empty initially."""
    resp = client.get("/api/v1/systems")
    data = resp.get_json()
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/rf-chambers
# ---------------------------------------------------------------------------


def test_list_rf_chambers_returns_200(client):
    resp = client.get("/api/v1/rf-chambers")
    assert resp.status_code == 200


def test_list_rf_chambers_returns_json(client):
    resp = client.get("/api/v1/rf-chambers")
    data = resp.get_json()
    assert data is not None
    assert "chambers" in data
    assert "count" in data


def test_list_rf_chambers_count_matches(client):
    resp = client.get("/api/v1/rf-chambers")
    data = resp.get_json()
    assert data["count"] == len(data["chambers"])


def test_list_rf_chambers_contains_seeded_chamber(client):
    """conftest seeds one chamber (XL001); it must appear in the list."""
    resp = client.get("/api/v1/rf-chambers")
    data = resp.get_json()
    barcodes = [c["barcode"] for c in data["chambers"]]
    assert "XL001" in barcodes


def test_list_rf_chambers_has_expected_fields(client):
    resp = client.get("/api/v1/rf-chambers")
    data = resp.get_json()
    if data["chambers"]:
        chamber = data["chambers"][0]
        for field in ("barcode", "size", "ports", "purpose", "location", "owner"):
            assert field in chamber


# ---------------------------------------------------------------------------
# POST /api/v1/inventory/items — QR code generation parity (#91)
# ---------------------------------------------------------------------------


def test_create_inventory_item_generates_qr_code_row(app, client):
    """POST /api/v1/inventory/items must persist a non-NULL qr_code in the DB."""
    import tools.inventory.db as _inv_db

    payload = {
        "name": "Oscilloscope",
        "description": "Rigol DS1054Z",
        "quantity": 1,
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 201
    item_id = resp.get_json()["id"]

    item = _inv_db.get_item(item_id)
    assert item is not None
    assert item["qr_code"] is not None, "qr_code must be non-NULL after POST"
    assert item["qr_code"] == f"qr_{item_id}.png"


def test_create_inventory_item_generates_qr_png_file(app, client):
    """POST /api/v1/inventory/items must write the QR PNG via the object storage layer.

    With OBJECT_STORAGE_BACKEND=local (the test default), the PNG is stored under
    the LocalFilesystemStorage root (DATA_DIR/uploads/).  We verify via url_for()
    rather than hard-coding the old generated/inventory/ path (#29).
    """
    payload = {
        "name": "Power Supply",
        "description": "Keysight E3631A",
        "quantity": 2,
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 201
    item_id = resp.get_json()["id"]

    storage = app.config.get("OBJECT_STORAGE")
    assert storage is not None, "OBJECT_STORAGE not initialised"
    qr_key = f"qr_{item_id}.png"
    resolved = storage.url_for(qr_key)
    import os
    assert os.path.exists(resolved), f"QR PNG not found at resolved path {resolved!r}"


def test_create_inventory_item_qr_failure_does_not_break_creation(app, client, monkeypatch):
    """If QR generation raises, item creation must still succeed (defensive parity)."""
    import qrcode as _qrcode

    monkeypatch.setattr(_qrcode, "make", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("qr failure")))

    payload = {
        "name": "Multimeter",
        "description": "Fluke 87V",
        "quantity": 3,
        "min_stock": 1,
    }
    resp = _post_json(client, "/api/v1/inventory/items", payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert "id" in data
