#!/usr/bin/env python3
"""Cancel test Jira tickets created during testing.

This script cancels the test tickets that were created during code testing
and adds a comment explaining they were test tickets.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from services.jira_service import JiraService, JiraServiceError

load_dotenv()

# List of test ticket IDs from VS Code Test Tickets filter
TEST_TICKETS = [
    "QENG-16577",
    "QENG-16578",
    "QENG-16579",
    "QENG-16580",
    "QENG-16582",
    "QENG-16583",
    "QENG-16584",
    "QENG-16585",
    "QENG-16563",
    "QENG-16564",
    "QENG-16565",
    "QENG-16566",
    "QENG-16567",
    "QENG-16568",
    "QENG-16569",
    "QENG-16570",
    "QENG-16571",
    "QENG-16572",
    "QENG-16573",
    "QENG-16450",
    "QENG-16555",
    "QENG-16558",
]

CANCEL_COMMENT = (
    "🤖 This ticket was created via AI Agent for automated code testing purposes. "
    "It has been automatically cancelled as it is not a real lab request. "
    "No action required."
)


def main():
    """Cancel all test tickets."""
    print("=" * 70)
    print("CANCEL TEST JIRA TICKETS")
    print("=" * 70)
    print(f"\nThis will cancel {len(TEST_TICKETS)} test tickets.")
    print("\nComment to be added:")
    print(f'  "{CANCEL_COMMENT}"')
    print()
    
    response = input("Type 'yes' to proceed with cancellation: ")
    if response.lower() != 'yes':
        print("Aborted.")
        return 0
    
    print()
    jira = JiraService()
    
    success_count = 0
    failed_tickets = []
    
    for i, ticket_id in enumerate(TEST_TICKETS, 1):
        try:
            print(f"[{i}/{len(TEST_TICKETS)}] Cancelling {ticket_id}...", end=" ")
            # Use transition_issue_by_name with resolution field passed in the transition
            # The "Cancelled" transition requires resolution to be set as part of the transition
            jira.transition_issue_by_name(
                ticket_id, 
                "Cancelled",
                fields={"resolution": {"name": "Cancelled"}},
                comment=CANCEL_COMMENT
            )
            print("✓")
            success_count += 1
        except JiraServiceError as e:
            print(f"✗ Failed: {e}")
            failed_tickets.append((ticket_id, str(e)))
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            failed_tickets.append((ticket_id, str(e)))
    
    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✓ Successfully cancelled: {success_count}/{len(TEST_TICKETS)} tickets")
    
    if failed_tickets:
        print(f"\n✗ Failed to cancel: {len(failed_tickets)} tickets")
        for ticket_id, error in failed_tickets:
            print(f"  - {ticket_id}: {error}")
        return 1
    else:
        print("\n🎉 All test tickets successfully cancelled!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
