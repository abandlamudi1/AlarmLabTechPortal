"""Migrate existing systems to use location_number and location_name fields."""
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.system_locator import db

def main():
    print("=" * 80)
    print("Migrating System Locator to Location Number + Location Name")
    print("=" * 80)
    print()
    
    # Initialize database (runs migrations)
    print("Running database migrations...")
    db.init_db()
    print("✓ Database schema updated")
    print()
    
    # Show migrated systems
    print("Checking migrated systems...")
    systems = db.list_systems()
    
    migrated_count = 0
    for system in systems:
        if system.get("location_number"):
            migrated_count += 1
            print(f"  ✓ {system['name']}")
            print(f"    Location Number: {system['location_number']}")
            print(f"    Location Name: {system.get('location_name') or '(not set)'}")
            print()
    
    print("=" * 80)
    print(f"Migration complete! {migrated_count} systems updated.")
    print("=" * 80)

if __name__ == "__main__":
    main()
