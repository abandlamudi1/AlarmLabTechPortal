#!/usr/bin/env python3
"""Test workflow transitions for Lab Request tickets.

⚠️⚠️⚠️ WARNING: CREATES REAL JIRA TICKETS ⚠️⚠️⚠️

This script creates and transitions actual tickets in the QENG Jira project!
Only run this when you specifically want to test workflow transitions.

Usage:
    python scripts/test_workflow_transitions.py

NOTE: This script is NOT run by 'pytest' or 'run all tests'.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from services.jira_service import JiraService

load_dotenv()


def main():
    """Test full workflow transitions."""
    jira = JiraService()
    
    print("=" * 70)
    print("⚠️  LAB REQUEST WORKFLOW TRANSITION TEST ⚠️")
    print("⚠️  CREATES REAL JIRA TICKETS IN QENG PROJECT ⚠️")
    print("=" * 70)
    
    response = input("\nType 'yes' to continue and create a real Jira ticket: ")
    if response.lower() != 'yes':
        print("Aborted.")
        return 0
    print()
    
    # Create a test ticket
    print("\n[1] Creating test Lab Request...")
    try:
        issue_key = jira.create_lab_request(
            summary="Workflow Transition Test Ticket",
            description="Testing all workflow transitions",
            assignee="bbrice",
            priority="P5: Nice to Have",
            lab_request_type="Lab setup",
            deadline=datetime.now().date().isoformat(),
        )
        print(f"✓ Created: {issue_key}")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return 1
    
    # Test On Hold transition
    print(f"\n[2] Transitioning to On Hold...")
    try:
        jira.transition_to_on_hold(issue_key, comment="Testing On Hold transition")
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        print(f"✓ Status: {status}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test back to Defining Requirements
    print(f"\n[3] Transitioning back to Defining Requirements...")
    try:
        jira.transition_to_defining_requirements(issue_key, comment="Back to defining")
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        print(f"✓ Status: {status}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test Pending Staff transition
    print(f"\n[4] Transitioning to Pending Staff...")
    try:
        jira.transition_to_pending_staff(issue_key, comment="Awaiting resources")
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        print(f"✓ Status: {status}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test In Progress transition (requires Planned End Date and High Level Estimate)
    print(f"\n[5] Transitioning to In Progress...")
    try:
        planned_date = (datetime.now() + timedelta(days=14)).date()
        
        jira.transition_to_in_progress(
            issue_key,
            planned_end_date=planned_date.isoformat(),  # YYYY-MM-DD format
            high_level_estimate="Small",
            comment="Starting work"
        )
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        print(f"✓ Status: {status}")
        print(f"  Planned End Date: {planned_date.isoformat()}")
        print(f"  High Level Estimate: Small")
    except Exception as e:
        print(f"✗ Failed: {e}")
        print("  Note: May need to verify custom field IDs for Planned End Date and High Level Estimate")
    
    # Test Testing transition
    print(f"\n[6] Transitioning to Testing...")
    try:
        jira.transition_to_testing(issue_key, comment="Ready for testing")
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        print(f"✓ Status: {status}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test Close transition (requires Resolution)
    print(f"\n[7] Transitioning to Closed...")
    try:
        jira.transition_to_closed(issue_key, resolution="Done", comment="Test complete")
        issue = jira.get_issue(issue_key)
        status = issue['fields']['status']['name']
        resolution = issue['fields'].get('resolution', {})
        resolution_name = resolution.get('name', 'N/A') if resolution else 'N/A'
        print(f"✓ Status: {status}")
        print(f"  Resolution: {resolution_name}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    print("\n" + "=" * 70)
    print(f"VIEW TICKET: {os.getenv('JIRA_URL')}/browse/{issue_key}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
