#!/usr/bin/env python3
"""Test cancelling a single ticket."""
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
    comment = "🤖 Test ticket - cancelling via direct transition"
    
    print(f"Attempting to cancel {ticket_id}")
    print(f"Comment: {comment}")
    print()
    
    try:
        jira.transition_issue_by_name(
            ticket_id, 
            "Cancelled",
            fields={"resolution": {"name": "Cancelled"}},
            comment=comment
        )
        print("✓ Success!")
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
