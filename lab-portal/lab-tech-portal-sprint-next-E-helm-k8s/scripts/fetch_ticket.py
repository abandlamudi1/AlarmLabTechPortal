"""Quick script to fetch and display a Jira ticket's details."""
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import services
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.jira_service import JiraService, JiraServiceError


def fetch_and_display_ticket(issue_key: str):
    """Fetch a ticket and display its key fields."""
    try:
        jira = JiraService()
        issue = jira.get_issue(issue_key)
        
        fields = issue.get("fields", {})
        
        print(f"\n{'='*80}")
        print(f"Ticket: {issue.get('key')}")
        print(f"{'='*80}\n")
        
        print(f"Summary: {fields.get('summary', 'N/A')}")
        print(f"\nStatus: {fields.get('status', {}).get('name', 'N/A')}")
        
        issue_type = fields.get('issuetype', {})
        print(f"Issue Type: {issue_type.get('name', 'N/A')}")
        
        assignee = fields.get('assignee')
        if assignee:
            print(f"Assignee: {assignee.get('displayName', 'N/A')} ({assignee.get('name', 'N/A')})")
        else:
            print("Assignee: Unassigned")
        
        print(f"\n{'='*80}")
        print("DESCRIPTION:")
        print(f"{'='*80}\n")
        
        description = fields.get('description', '')
        if description:
            print(description)
        else:
            print("(No description)")
        
        print(f"\n{'='*80}")
        print("ALL FIELDS (for parser development):")
        print(f"{'='*80}\n")
        
        # Print all custom fields that might contain data we need
        for field_name, field_value in sorted(fields.items()):
            if field_value and not isinstance(field_value, dict) or (isinstance(field_value, dict) and field_value):
                # Skip empty values and common fields we already printed
                if field_name not in ['description', 'summary', 'status', 'issuetype', 'assignee', 'creator', 'reporter']:
                    if isinstance(field_value, str) and field_value.strip():
                        print(f"{field_name}: {field_value[:100]}...")
                    elif isinstance(field_value, dict):
                        if 'value' in field_value:
                            print(f"{field_name}: {field_value['value']}")
                        elif 'name' in field_value:
                            print(f"{field_name}: {field_value['name']}")
        
        return issue
        
    except JiraServiceError as e:
        print(f"Error fetching ticket: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ticket = sys.argv[1]
    else:
        ticket = "IAT-5063"
    
    fetch_and_display_ticket(ticket)
