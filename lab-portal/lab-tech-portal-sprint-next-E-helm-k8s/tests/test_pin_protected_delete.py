"""Test PIN-protected hard delete functionality."""
from werkzeug.datastructures import MultiDict

from tools.system_locator import db as systems_db


def test_hard_delete_with_correct_pin(client):
    """Test that hard delete works with correct PIN."""
    # Create a system profile
    system_id = systems_db.create_system(
        {
            "name": "Test Delete System",
            "location_number": "10-640",
            "location_name": "Automation Lab",
            "status": "Active",
            "notes": "To be deleted",
            "jira_tickets": "",
        },
        [("CID", "DELETE-TEST-123")],
    )
    
    # Verify system exists
    system = systems_db.get_system(system_id)
    assert system is not None
    assert system["name"] == "Test Delete System"
    
    # Perform hard delete with correct PIN
    response = client.post(
        f"/systems/{system_id}/hard-delete",
        data={"pin": "9420"},
        follow_redirects=True
    )
    
    assert response.status_code == 200
    assert b"permanently deleted" in response.data
    
    # Verify system is actually deleted
    system_after = systems_db.get_system(system_id)
    assert system_after is None


def test_hard_delete_with_incorrect_pin(client):
    """Test that hard delete fails with incorrect PIN."""
    # Create a system profile
    system_id = systems_db.create_system(
        {
            "name": "Test Protected System",
            "location_number": "10-510",
            "location_name": "QE Lab",
            "status": "Active",
            "notes": "Should not be deleted",
            "jira_tickets": "",
        },
        [("CID", "PROTECTED-456")],
    )
    
    # Verify system exists
    system = systems_db.get_system(system_id)
    assert system is not None
    
    # Attempt hard delete with incorrect PIN
    response = client.post(
        f"/systems/{system_id}/hard-delete",
        data={"pin": "0000"},  # Wrong PIN
        follow_redirects=True
    )
    
    assert response.status_code == 200
    assert b"Incorrect PIN" in response.data
    
    # Verify system still exists
    system_after = systems_db.get_system(system_id)
    assert system_after is not None
    assert system_after["name"] == "Test Protected System"


def test_hard_delete_with_empty_pin(client):
    """Test that hard delete fails with empty PIN."""
    # Create a system profile
    system_id = systems_db.create_system(
        {
            "name": "Test Empty PIN System",
            "location_number": "10-630",
            "location_name": "Product Testing Lab",
            "status": "Active",
            "notes": "Should not be deleted",
            "jira_tickets": "",
        },
        [("CID", "EMPTY-PIN-789")],
    )
    
    # Attempt hard delete with empty PIN
    response = client.post(
        f"/systems/{system_id}/hard-delete",
        data={"pin": ""},  # Empty PIN
        follow_redirects=True
    )
    
    assert response.status_code == 200
    assert b"Incorrect PIN" in response.data
    
    # Verify system still exists
    system_after = systems_db.get_system(system_id)
    assert system_after is not None


def test_hard_delete_removes_identifiers(client):
    """Test that hard delete also removes associated identifiers."""
    # Create a system profile with multiple identifiers
    system_id = systems_db.create_system(
        {
            "name": "Test Multi Identifier System",
            "location_number": "11-050",
            "location_name": "DE Lab",
            "status": "Active",
            "notes": "Has multiple identifiers",
            "jira_tickets": "",
        },
        [
            ("CID", "MULTI-111"),
            ("MAC", "AA:BB:CC:DD:EE:FF"),
            ("Login", "test_user"),
        ],
    )
    
    # Verify system and identifiers exist
    system = systems_db.get_system(system_id)
    assert system is not None
    assert len(system["identifiers"]) == 3
    
    # Perform hard delete with correct PIN
    response = client.post(
        f"/systems/{system_id}/hard-delete",
        data={"pin": "9420"},
        follow_redirects=True
    )
    
    assert response.status_code == 200
    
    # Verify system and identifiers are deleted
    system_after = systems_db.get_system(system_id)
    assert system_after is None
    
    # Verify identifiers cannot be found
    identifier_search = systems_db.find_system_by_identifier("MULTI-111")
    assert identifier_search is None
