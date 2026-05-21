#!/usr/bin/env bash
# Test script to create a Lab Request via JiraService

set -e

# Set required environment variables from .env file
# These should already be loaded if you're using the Flask app,
# but we ensure they're available for standalone script execution
export JIRA_URL="${JIRA_URL}"
export JIRA_PAT="${JIRA_PAT}"

if [ -z "$JIRA_PAT" ]; then
    echo "Error: JIRA_PAT environment variable must be set"
    exit 1
fi

echo "Running Lab Request creation test..."
echo "JIRA_URL: $JIRA_URL"
echo ""

cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d venv ]; then
    source venv/bin/activate
fi

# Run the test
python -m pytest tests/test_jira_service.py::test_create_lab_request_integration -v -s
