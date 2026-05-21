#!/usr/bin/env python3
"""Find custom field IDs for workflow transitions."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv()

jira_url = os.getenv('JIRA_URL')
pat = os.getenv('JIRA_PAT')
headers = {'Authorization': f'Bearer {pat}', 'Accept': 'application/json'}

# Search for a Lab Request in In Progress state
params = {
    'jql': 'project=QENG AND issuetype="Lab Request " AND status="In Progress"',
    'fields': '*all',
    'maxResults': 1
}
r = requests.get(f'{jira_url}/rest/api/2/search', params=params, headers=headers)
if r.status_code == 200:
    data = r.json()
    if data['issues']:
        issue = data['issues'][0]
        print(f"Found ticket: {issue['key']}")
        fields = issue['fields']
        
        # Print custom fields that look like dates or estimates
        print('\nRelevant custom fields:')
        for key in sorted(fields.keys()):
            if key.startswith('customfield'):
                value = fields[key]
                if value is not None:
                    value_str = str(value)[:100]
                    # Look for date-like or estimate-like values
                    if any(term in value_str.lower() for term in ['/', 'date', 'small', 'medium', 'large', 'estimate']):
                        if isinstance(value, dict):
                            print(f'{key}: {value.get("value", value.get("name", value_str))}')
                        else:
                            print(f'{key}: {value_str}')
    else:
        print('No Lab Requests found in In Progress state')
else:
    print(f'Search failed: {r.status_code}')
    print(r.text)
