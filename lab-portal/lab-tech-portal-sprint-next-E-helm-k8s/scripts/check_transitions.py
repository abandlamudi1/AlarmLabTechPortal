#!/usr/bin/env python3
"""Discover actual transition names for each workflow state."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from services.jira_service import JiraService

load_dotenv()

jira = JiraService()
issue_key = "QENG-16556"

# Get current status
issue = jira.get_issue(issue_key, fields="status")
current_status = issue['fields']['status']['name']
print(f"Current status: {current_status}")
print(f"\nAvailable transitions:")

result = jira.get_transitions(issue_key)
transitions = result.get('transitions', [])
for t in transitions:
    print(f'  {t["id"]}: "{t["name"]}"')
