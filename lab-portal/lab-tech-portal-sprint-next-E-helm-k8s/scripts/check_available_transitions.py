#!/usr/bin/env python3
"""Check available transitions for a test ticket."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from services.jira_service import JiraService

load_dotenv()

def main():
    jira = JiraService()
    
    ticket_id = "QENG-16577"
    print(f"Checking transitions for {ticket_id}")
    print("=" * 70)
    
    # Get current issue status
    issue = jira.get_issue(ticket_id)
    current_status = issue['fields']['status']['name']
    print(f"Current Status: {current_status}")
    print()
    
    # Get available transitions
    result = jira.get_transitions(ticket_id)
    transitions = result.get('transitions', [])
    
    print(f"Available transitions ({len(transitions)}):")
    for t in transitions:
        print(f"  - {t['name']} (ID: {t['id']})")
        # Check if there are any fields required for this transition
        if t.get('fields'):
            print(f"    Fields: {t.get('fields')}")
        # Check if resolution is mentioned
        if t['name'] == 'Cancelled':
            print(f"    Full transition info: {t}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
