#!/usr/bin/env python3
"""Diagnostic script to test Jira authentication."""
import base64
import os
import sys

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def test_auth():
    jira_url = os.getenv("JIRA_URL")
    pat = os.getenv("JIRA_PAT")

    if not jira_url or not pat:
        print("ERROR: JIRA_URL and JIRA_PAT environment variables must be set")
        sys.exit(1)

    print(f"JIRA_URL: {jira_url}")
    print(f"PAT length: {len(pat)} characters")
    print(f"PAT starts with: {pat[:10]}...")
    print()

    # Test Bearer token authentication
    print("Testing Bearer token authentication...")
    test_url = f"{jira_url}/rest/api/2/myself"
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/json",
    }

    print(f"Testing: {test_url}")
    try:
        response = requests.get(test_url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ SUCCESS! Authenticated as: {data.get('displayName')} ({data.get('name')})")
            return True
        else:
            print(f"✗ FAILED: {response.text[:200]}")
            return False
    except Exception as exc:
        print(f"✗ ERROR: {exc}")
        return False


if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
