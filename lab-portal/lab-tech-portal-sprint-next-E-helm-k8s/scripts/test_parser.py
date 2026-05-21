"""Test the description parser with real Jira tickets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.jira_service import JiraService, JiraServiceError
from tools.system_locator.description_parser import parse_ticket_for_system, DescriptionParser


def test_parser_with_ticket(issue_key: str):
    """Fetch a ticket and parse it."""
    try:
        jira = JiraService()
        issue = jira.get_issue(issue_key)
        
        print(f"\n{'='*80}")
        print(f"Testing Parser with Ticket: {issue_key}")
        print(f"{'='*80}\n")
        
        fields = issue.get("fields", {})
        print(f"Original Summary: {fields.get('summary', '')}\n")
        
        # Parse the ticket
        system_data = parse_ticket_for_system(issue)
        
        print(f"{'='*80}")
        print("PARSED SYSTEM DATA:")
        print(f"{'='*80}\n")
        
        print(f"System Name: {system_data['name']}")
        print(f"Building: {system_data['building']}")
        print(f"Room: {system_data['room']}")
        print(f"Sub-location: {system_data['sub_location']}")
        print(f"Status: {system_data['status']}")
        print(f"Jira Issue: {system_data['jira_issue_key']}")
        
        print(f"\nIdentifiers ({len(system_data['identifiers'])}):")
        for identifier in system_data['identifiers']:
            print(f"  - {identifier['label']:15} : {identifier['value']:30} (from {identifier['source']})")
        
        print(f"\nNotes:")
        print(f"{'-'*80}")
        notes_lines = system_data['notes'].split('\n')
        for line in notes_lines:  #Show all lines
            print(line)
        
        print(f"\n{'='*80}")
        print(f"Devices List:")
        print(f"{'='*80}")
        
        # Also test devices extraction directly
        description = fields.get("description", "")
        devices = DescriptionParser.extract_devices(description)
        for device in devices:
            print(f"  - {device}")
        if not devices:
            print("  (No devices extracted)")
        
        return system_data
        
    except JiraServiceError as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ticket = sys.argv[1]
    else:
        ticket = "IAT-5063"
    
    result = test_parser_with_ticket(ticket)
    
    if result:
        print(f"\n{'='*80}")
        print("✅ Parser Test Successful!")
        print(f"{'='*80}")
