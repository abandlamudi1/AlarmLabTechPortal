"""Test the updated jira_import_service with parser integration."""
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.jira_service import JiraService
from tools.system_locator.jira_import_service import JiraImportService, JiraFieldMapping
from tools.system_locator.lab_request_ingestion import LabRequestIngestionClient
from tools.system_locator.jira_service_loader import JiraServiceLoader

def main():
    # Set up the import service like in system_locator_app
    jira_service = JiraService()
    loader = JiraServiceLoader(jira_service)
    client = LabRequestIngestionClient(loader=loader, cache_ttl_seconds=300)
    
    # Use default field mapping
    field_mapping = JiraFieldMapping({})
    
    import_service = JiraImportService(client, field_mapping)
    
    print("=" * 80)
    print("Testing Import Service with IAT-5063")
    print("=" * 80)
    print()
    
    # Build preview for the specific issue
    candidates = import_service.build_preview(issue_keys=["IAT-5063"])
    
    if not candidates:
        print("ERROR: No candidates returned")
        return
    
    candidate = candidates[0]
    
    print(f"Issue Key: {candidate.issue_key}")
    print(f"System Name: {candidate.system_name}")
    print(f"Status: {candidate.mapped_status} (from Jira: {candidate.jira_status})")
    print()
    
    print(f"Location (complete: {candidate.location_complete}):")
    print(f"  Building: {candidate.location['building']}")
    print(f"  Room: {candidate.location['room']}")
    print(f"  Sub-location: {candidate.location['sub_location']}")
    if candidate.missing_location_fields:
        print(f"  Missing: {', '.join(candidate.missing_location_fields)}")
    print()
    
    print(f"Identifiers ({len(candidate.identifiers)}):")
    for ident in candidate.identifiers:
        source = getattr(ident, 'source', 'jira')
        print(f"  - {ident.label:20} : {ident.value:30} ({source})")
    print()
    
    print("Notes (first 500 chars):")
    print("-" * 80)
    print(candidate.notes[:500])
    if len(candidate.notes) > 500:
        print(f"\n... ({len(candidate.notes) - 500} more characters)")
    print("-" * 80)
    print()
    
    print("=" * 80)
    print("✅ Import Service Test Complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
