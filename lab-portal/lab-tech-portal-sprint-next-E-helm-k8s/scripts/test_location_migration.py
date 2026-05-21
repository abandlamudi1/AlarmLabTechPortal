"""Test script to verify location model migration."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.system_locator import db

def test_location_migration():
    """Verify location fields are working correctly."""
    print("=" * 70)
    print("Testing Location Model Migration")
    print("=" * 70)
    
    # Test 1: Create a system with new location fields
    print("\n✓ Test 1: Creating system with location_number and location_name...")
    test_data = {
        "name": "Test Migration System",
        "location_number": "10-640",
        "location_name": "Automation Lab",
        "status": "Active",
        "notes": "Test system for migration verification",
    }
    
    system_id = db.create_system(test_data, [("CID", "TEST-12345")])
    print(f"  Created system ID: {system_id}")
    
    # Test 2: Retrieve and verify
    print("\n✓ Test 2: Retrieving system and verifying fields...")
    system = db.get_system(system_id)
    
    assert system is not None, "System not found!"
    assert system["location_number"] == "10-640", f"Expected '10-640', got '{system['location_number']}'"
    assert system["location_name"] == "Automation Lab", f"Expected 'Automation Lab', got '{system['location_name']}'"
    
    # Verify legacy fields are NULL (not used anymore)
    assert system["building"] is None, "Legacy 'building' field should be NULL"
    assert system["room"] is None, "Legacy 'room' field should be NULL"
    assert system["sub_location"] is None, "Legacy 'sub_location' field should be NULL"
    
    print(f"  ✓ location_number: {system['location_number']}")
    print(f"  ✓ location_name: {system['location_name']}")
    print(f"  ✓ building (legacy): {system['building']} (correctly NULL)")
    print(f"  ✓ room (legacy): {system['room']} (correctly NULL)")
    print(f"  ✓ sub_location (legacy): {system['sub_location']} (correctly NULL)")
    
    # Test 3: Update system
    print("\n✓ Test 3: Updating system location...")
    update_data = {
        "name": "Test Migration System",
        "location_number": "10-742",
        "location_name": "QE Lab - Floor 10",
        "status": "Active",
        "notes": "Updated location",
    }
    db.update_system(system_id, update_data, [("CID", "TEST-12345")])
    
    updated_system = db.get_system(system_id)
    assert updated_system["location_number"] == "10-742"
    assert updated_system["location_name"] == "QE Lab - Floor 10"
    print(f"  ✓ Updated location_number: {updated_system['location_number']}")
    print(f"  ✓ Updated location_name: {updated_system['location_name']}")
    
    # Test 4: Search functionality
    print("\n✓ Test 4: Testing search with new location fields...")
    results = db.search_systems("10-742")
    assert len(results) >= 1, "Search should find the system by location_number"
    print(f"  ✓ Found {len(results)} system(s) with location_number '10-742'")
    
    # Clean up
    print("\n✓ Test 5: Cleaning up test data...")
    db.delete_system(system_id)
    print(f"  ✓ System {system_id} marked as Decommissioned")
    
    print("\n" + "=" * 70)
    print("✓ All migration tests passed successfully!")
    print("=" * 70)
    print("\nSummary:")
    print("  • Location Number and Location Name are working correctly")
    print("  • Legacy fields (building, room, sub_location) are NULL as expected")
    print("  • Create, read, update operations work correctly")
    print("  • Search functionality includes new location fields")
    

if __name__ == "__main__":
    try:
        test_location_migration()
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
