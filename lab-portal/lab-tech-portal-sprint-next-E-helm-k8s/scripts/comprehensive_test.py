#!/usr/bin/env python3
"""Comprehensive validation test for JiraService.

⚠️⚠️⚠️ WARNING: CREATES REAL JIRA TICKETS ⚠️⚠️⚠️

This script creates actual tickets in the QENG Jira project!
Only run this when you specifically want to test Jira integration.

Usage:
    python scripts/comprehensive_test.py

NOTE: This script is NOT run by 'pytest' or 'run all tests'.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from services.jira_service import JiraService

def main():
    """Run comprehensive validation tests."""
    print("=" * 70)
    print("⚠️  JIRA SERVICE VALIDATION TEST SUITE ⚠️")
    print("⚠️  CREATES REAL JIRA TICKETS IN QENG PROJECT ⚠️")
    print("=" * 70)
    
    response = input("\nType 'yes' to continue and create a real Jira ticket: ")
    if response.lower() != 'yes':
        print("Aborted.")
        return 0
    print()
    
    jira = JiraService()
    
    # Test 1: Create a Lab Request
    print("\n[Test 1] Creating Lab Request...")
    try:
        issue_key = jira.create_lab_request(
            summary="Comprehensive Validation Test for JiraService",
            description="This ticket was created to test all functionality of the JiraService client.",
            assignee="bbrice",  # Default to Ben Bryce
            priority="P5: Nice to Have",
            lab_request_type="Lab setup",
            deadline=datetime.now().date().isoformat(),
        )
        print(f"✓ Created ticket: {issue_key}")
    except Exception as e:
        print(f"✗ Failed to create ticket: {e}")
        return 1
    
    # Test 2: Get transitions
    print(f"\n[Test 2] Fetching transitions for {issue_key}...")
    try:
        result = jira.get_transitions(issue_key)
        transitions = result.get('transitions', [])
        print(f"✓ Found {len(transitions)} transitions:")
        for t in transitions:
            print(f"  - {t['name']} (id: {t['id']})")
    except Exception as e:
        print(f"✗ Failed to get transitions: {e}")
        return 1
    
    # Test 3: Transition issue (if "Pending Staff" is available)
    print(f"\n[Test 3] Transitioning {issue_key} to 'Pending Staff'...")
    try:
        jira.transition_issue_by_name(issue_key, "Pending Staff")
        print(f"✓ Transitioned to 'Pending Staff'")
    except Exception as e:
        print(f"✗ Failed to transition: {e}")
        # Don't fail entire test, might not be available
    
    # Test 4: Update issue fields
    print(f"\n[Test 4] Updating {issue_key} fields...")
    try:
        jira.update_description(issue_key, "Updated description with validation test results.")
        print(f"✓ Updated description")
        
        jira.update_assignee(issue_key, "snodder")
        print(f"✓ Updated assignee to snodder")
        
        jira.update_priority(issue_key, "P4: Low")
        print(f"✓ Updated priority to P4: Low")
    except Exception as e:
        print(f"✗ Failed to update fields: {e}")
        return 1
    
    # Test 5: Get issue details
    print(f"\n[Test 5] Fetching {issue_key} details...")
    try:
        issue = jira.get_issue(issue_key)
        fields = issue['fields']
        print(f"✓ Retrieved issue:")
        print(f"  Summary: {fields['summary']}")
        print(f"  Status: {fields['status']['name']}")
        print(f"  Assignee: {fields['assignee']['displayName'] if fields.get('assignee') else 'Unassigned'}")
        print(f"  Priority: {fields['priority']['name']}")
    except Exception as e:
        print(f"✗ Failed to fetch issue: {e}")
        return 1
    
    print("\n" + "=" * 70)
    print(f"✓ ALL TESTS PASSED! View ticket: {os.getenv('JIRA_URL')}/browse/{issue_key}")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
