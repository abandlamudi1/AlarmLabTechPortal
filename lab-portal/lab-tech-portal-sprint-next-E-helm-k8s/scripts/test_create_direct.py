#!/usr/bin/env python3
"""Direct test of Lab Request creation.

⚠️⚠️⚠️ WARNING: CREATES REAL JIRA TICKETS ⚠️⚠️⚠️

This script creates actual tickets in the QENG Jira project using direct REST API calls!
Only run this when you specifically want to test direct Jira API integration.

Usage:
    python scripts/test_create_direct.py

NOTE: This script is NOT run by 'pytest' or 'run all tests'.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("⚠️  DIRECT JIRA API TEST ⚠️")
print("⚠️  CREATES REAL JIRA TICKETS IN QENG PROJECT ⚠️")
print("=" * 70)

response = input("\nType 'yes' to continue and create a real Jira ticket: ")
if response.lower() != 'yes':
    print("Aborted.")
    exit(0)
print()

jira_url = os.getenv('JIRA_URL')
pat = os.getenv('JIRA_PAT')

payload = {
    'fields': {
        'project': {'key': 'QENG'},
        'issuetype': {'id': '13901'},  # Lab Request ID
        'summary': 'Test for Ben using JIRA REST API',
        'description': 'This is an automated test ticket.',
        # 'assignee': {'name': 'unassigned'},  # Skip assignee - will default
        'priority': {'name': 'P5: Nice to Have'},
        'customfield_18703': {'value': 'Lab setup'},
        'customfield_16802': {'value': 'Support Team'},
        'customfield_25100': {'value': 'Quality Engineering'},
        'customfield_18053': '2026-02-06'
    }
}

headers = {
    'Authorization': f'Bearer {pat}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

print('Sending to:', f'{jira_url}/rest/api/2/issue')
print('Payload:', json.dumps(payload, indent=2))
print()

r = requests.post(f'{jira_url}/rest/api/2/issue', json=payload, headers=headers)
print(f'Status: {r.status_code}')
print(f'Response: {r.text}')
