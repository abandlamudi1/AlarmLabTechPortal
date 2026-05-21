from datetime import datetime

import os
import pytest

from tools.print_requests import db as print_requests_db
from tools.print_requests.print_requests_app import _create_jira_ticket


@pytest.mark.creates_jira_tickets
def test_print_request_creates_jira_ticket(app):
    required = ["JIRA_URL", "JIRA_PAT"]
    if any(not os.getenv(var) for var in required):
        pytest.skip("Missing Jira credentials for integration test")

    app.config["PRINT_REQUESTS_CREATE_JIRA"] = True
    request_id = print_requests_db.create_request(
        requester="Jira Integration",
        team="QE",
        request_type="new_design",
        selected_model_details=None,
        quantity=1,
        due_date=None,
        description="Jira ticket creation test",
        created_at=datetime(2026, 2, 23, 10, 0, 0),
    )

    with app.app_context():
        _create_jira_ticket(request_id)

    record = print_requests_db.get_request(request_id)
    assert record is not None
    assert record["jira_ticket_key"]
    assert str(record["jira_ticket_key"]).startswith("QENG-")
