"""Test the Jira import endpoint to see the error."""
import requests
import json

# Test the preview endpoint
url = "http://127.0.0.1:5000/systems/jira-import/preview"
data = {
    "issue_keys": "IAT-5063"
}

print("Testing preview endpoint...")
print(f"POST {url}")
print(f"Data: {data}")
print()

try:
    response = requests.post(url, data=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(response.text[:1000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
