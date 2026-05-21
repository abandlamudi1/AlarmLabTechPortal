from io import BytesIO

from tools.print_requests import db as print_requests_db
from datetime import date

from tools.print_requests.print_requests_app import MODEL_LIBRARY, _compute_default_deadline


def test_library_page_lists_devices(client):
    response = client.get("/print-requests/")
    assert response.status_code == 200
    body = response.data.decode()
    assert "3D Print Model Library" in body
    assert "Doorbell 770" in body
    assert "View models" in body
    assert "View submitted requests" in body


def test_device_library_page_lists_models(client):
    response = client.get("/print-requests/library/770")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Doorbell 770" in body
    assert "Doorbell 770 Holder – Desk Mount" in body
    assert "Submit request for this model" in body


def test_queue_page_shows_requests(client):
    selected = {
        "category": "doorbell_holders",
        "category_label": "Doorbell holders",
        "device": "770",
        "device_label": "Doorbell 770",
        "variant": "desk",
        "variant_label": "Desk mounted",
    }
    print_requests_db.create_request(
        requester="Jordan",
        team="QE",
        request_type="existing_model",
        selected_model_details=selected,
        quantity=2,
        due_date="2026-02-05",
        description="Existing model requested: Doorbell 770 Holder – Desk Mount",
    )

    response = client.get("/print-requests/requests")
    assert response.status_code == 200
    body = response.data.decode()
    assert "3D Print Queue" in body
    assert "Jordan" in body
    assert "Existing Model" in body
    assert "Not yet created" in body


def test_create_request_with_upload(client):
    payload = {
        "requester": "Taylor",
        "team": "QE",
        "request_type": "upload_file",
        "description": "Print spare cover",
    }
    file_stream = BytesIO(b"solid model")
    file_stream.seek(0)
    data = {**payload, "upload": (file_stream, "cover.stl")}

    response = client.post("/print-requests/new", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Request submitted" in body

    records = print_requests_db.list_requests()
    assert records
    stored = records[0]
    assert stored["requester"] == "Taylor"
    assert stored["uploaded_file_path"]
    assert stored["quantity"] == 1
    assert stored["due_date"] is None
    assert stored["selected_model_details"] == {}


def test_new_design_with_image_upload(client):
    payload = {
        "requester": "Sage",
        "team": "Design",
        "request_type": "new_design",
        "description": "Need a reference image for the custom housing",
    }
    file_stream = BytesIO(b"image bytes")
    file_stream.seek(0)
    data = {**payload, "design_image": (file_stream, "housing.png")}

    response = client.post("/print-requests/new", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Request submitted" in body

    records = print_requests_db.list_requests()
    assert records
    stored = records[0]
    assert stored["request_type"] == "new_design"
    assert stored["uploaded_image_path"]


def test_new_design_requires_description(client):
    data = {
        "requester": "Morgan",
        "team": "QE",
        "request_type": "new_design",
        "description": "",
    }
    response = client.post("/print-requests/new", data=data, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Provide details for the new design" in body
    assert "Request submitted" not in body


def test_existing_model_submission_records_variant(client):
    model_entry = MODEL_LIBRARY[0]
    payload = {
        "requester": "Jamie",
        "team": "Hardware",
        "request_type": "existing_model",
        "model_device": model_entry["device"],
        "model_variant": model_entry["slug"],
        "quantity": "3",
        "due_date": "2026-02-10",
    }

    response = client.post("/print-requests/new", data=payload, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Request submitted" in body

    record = print_requests_db.list_requests()[0]
    assert record["quantity"] == 3
    assert record["due_date"] == "2026-02-10"
    assert record["selected_model_details"]["variant_label"] == model_entry["variant_label"]


def test_existing_model_requires_variant_selection(client):
    model_entry = MODEL_LIBRARY[0]
    payload = {
        "requester": "Peyton",
        "team": "Ops",
        "request_type": "existing_model",
        "model_device": model_entry["device"],
        "model_variant": "",
        "quantity": "1",
    }

    response = client.post("/print-requests/new", data=payload, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Select a valid model from the library." in body
    assert "Request submitted" not in body


def test_quantity_must_be_positive(client):
    initial_count = len(print_requests_db.list_requests())
    payload = {
        "requester": "Dana",
        "team": "QE",
        "request_type": "new_design",
        "description": "Need custom jig",
        "quantity": "0",
    }

    response = client.post("/print-requests/new", data=payload, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Enter a whole number greater than zero." in body
    assert len(print_requests_db.list_requests()) == initial_count


def test_due_date_validation_catches_invalid_format(client):
    payload = {
        "requester": "Riley",
        "team": "Hardware",
        "request_type": "new_design",
        "description": "Prototype fixture",
        "quantity": "1",
        "due_date": "02-31-2026",
    }

    response = client.post("/print-requests/new", data=payload, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Use the date picker to choose a valid date." in body
    assert "Request submitted" not in body


def test_form_prefills_when_model_query_provided(client):
    model_entry = MODEL_LIBRARY[0]
    response = client.get(f"/print-requests/new?model={model_entry['slug']}")
    assert response.status_code == 200
    body = response.data.decode()
    assert f'value="{model_entry["device"]}" selected' in body or f'value="{model_entry["device"]}" selected="selected"' in body
    assert f'value="{model_entry["slug"]}" data-device="{model_entry["device"]}"' in body


def test_request_detail_page_shows_request(client):
    request_id = print_requests_db.create_request(
        requester="Cameron",
        team="QE",
        request_type="new_design",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="Prototype clamp",
    )

    response = client.get(f"/print-requests/requests/{request_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "3D Print Request" in body
    assert "Cameron" in body
    assert "Prototype clamp" in body


def test_status_update_removes_closed_from_queue(client):
    request_id = print_requests_db.create_request(
        requester="Quinn",
        team="Lab",
        request_type="new_design",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="Alignment tool",
    )

    response = client.post(
        f"/print-requests/requests/{request_id}/status",
        data={"print_status": "Closed"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    queue_body = response.data.decode()
    assert "Alignment tool" not in queue_body

    record = print_requests_db.get_request(request_id)
    assert record is not None
    assert record["print_status"] == "Closed"


def test_default_deadline_uses_created_at_date():
    created_at = "2026-02-23T10:15:00"
    expected = date(2026, 3, 9).isoformat()
    assert _compute_default_deadline(created_at) == expected
