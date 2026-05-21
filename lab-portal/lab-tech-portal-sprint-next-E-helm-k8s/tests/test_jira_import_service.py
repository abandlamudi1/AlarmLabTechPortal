from tools.system_locator import db as systems_db
from tools.system_locator.jira_import_service import JiraFieldMapping, JiraImportService
from tools.system_locator.lab_request_ingestion import LabRequestIngestionClient


class _FakeLoader:
    def __init__(self, issues):
        self._issues = issues

    def load_lab_requests(self, *, project_keys=None, start_date=None, end_date=None, issue_keys=None, fields=None):
        if issue_keys:
            keys = set(issue_keys)
            return [issue for issue in self._issues if issue["key"] in keys]
        return list(self._issues)


def _make_issue(key, summary, status, description, fields):
    return {
        "key": key,
        "summary": summary,
        "status": status,
        "description": description,
        "fields": fields,
    }


def test_jira_import_creates_system(app):
    loader = _FakeLoader([
        _make_issue(
            "QEPR-101",
            "Thermal Rig",
            "In Progress",
            "Needs weekly calibration",
            {
                "location_number": "10-640",
                "location_name": "Automation Lab",
                "cid": "CID-5001",
                "login": "thermal_admin",
            },
        )
    ])

    client = LabRequestIngestionClient(loader=loader, cache_ttl_seconds=0)
    field_mapping = JiraFieldMapping.from_config(app.config)
    service = JiraImportService(client, field_mapping)

    preview = service.build_preview(issue_keys=["QEPR-101"])
    assert len(preview) == 1
    candidate = preview[0]
    assert candidate.mapped_status == "Maintenance"
    assert candidate.location_complete is True
    assert any(identifier.label == "CID" and identifier.value == "CID-5001" for identifier in candidate.identifiers)

    result = service.apply(issue_keys=["QEPR-101"])
    assert result.created == 1
    systems = systems_db.search_systems("Thermal Rig")
    assert systems
    stored = systems[0]
    assert stored["status"] == "Maintenance"
    full_record = systems_db.get_system(stored["id"])
    assert full_record["jira_issue_key"] == "QEPR-101"
    identifier_values = {item["value"] for item in full_record["identifiers"]}
    assert "CID-5001" in identifier_values
    assert "QEPR-101" in full_record["jira_tickets"]


def test_jira_import_updates_existing_and_flags_conflicts(app):
    base_id = systems_db.create_system(
        {
            "name": "Alpha Rig",
            "location_number": "10-510",
            "location_name": "QE Lab",
            "status": "Active",
            "notes": "Manual entry",
            "jira_issue_key": None,
            "jira_tickets": "",
        },
        [("CID", "CID-999")],
    )
    systems_db.create_system(
        {
            "name": "Beta Rig",
            "location_number": "11-050",
            "location_name": "DE Lab",
            "status": "Active",
            "notes": "Existing MAC",
            "jira_issue_key": None,
            "jira_tickets": "",
        },
        [("MAC", "AA-BB-CC-DD")],
    )

    loader = _FakeLoader([
        _make_issue(
            "QEPR-205",
            "Alpha Rig",
            "Blocked",
            "Awaiting parts",
            {
                "location_number": "10-510",
                "location_name": "",
                "cid": "CID-999",
                "mac": "AA-BB-CC-DD",
            },
        )
    ])

    client = LabRequestIngestionClient(loader=loader, cache_ttl_seconds=0)
    field_mapping = JiraFieldMapping.from_config(app.config)
    service = JiraImportService(client, field_mapping)

    preview = service.build_preview(issue_keys=["QEPR-205"])
    candidate = preview[0]
    assert candidate.existing_system is not None
    assert candidate.existing_system["id"] == base_id
    assert candidate.mapped_status == "Incomplete"
    assert candidate.location_complete is False
    assert candidate.missing_location_fields == ["location_name"]
    assert candidate.identifier_conflicts
    conflict_values = {conflict.value for conflict in candidate.identifier_conflicts}
    assert "AA-BB-CC-DD" in conflict_values

    result = service.apply(issue_keys=["QEPR-205"])
    assert result.updated == 1
    updated = systems_db.get_system(base_id)
    assert updated["status"] == "Incomplete"
    assert updated["jira_issue_key"] == "QEPR-205"
    identifiers = {item["value"] for item in updated["identifiers"]}
    assert "CID-999" in identifiers
    assert "AA-BB-CC-DD" not in identifiers
    assert updated["sub_location"] is None
