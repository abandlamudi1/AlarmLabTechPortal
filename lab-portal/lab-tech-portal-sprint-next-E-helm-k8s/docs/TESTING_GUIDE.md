# Testing Guide - Lab Tech Portal

## Overview

This project has two types of tests:

1. **Unit/Integration Tests** (pytest) - Safe tests that use test databases
2. **Jira Integration Tests** - ⚠️ Tests that create REAL Jira tickets

## Running Tests

### Default Test Run (Excludes Jira Ticket Creation)

Run all safe tests that don't create real Jira tickets:

```powershell
# Windows
python -m pytest

# macOS/Linux
python3 -m pytest
```

This automatically excludes tests marked with `@pytest.mark.creates_jira_tickets`.

### Running Specific Jira Integration Tests

⚠️ **WARNING**: These create REAL tickets in the QENG Jira project!

Run individual Jira ticket-creating tests:

```powershell
# Run a specific test
pytest -m creates_jira_tickets tests/test_jira_service.py::test_create_lab_request_integration
pytest -m creates_jira_tickets tests/test_print_requests_jira.py::test_print_request_creates_jira_ticket

# Run all Jira ticket-creating tests
pytest -m creates_jira_tickets

# Run with verbose output
pytest -m creates_jira_tickets -v
```

### Running Standalone Test Scripts

⚠️ **WARNING**: These create REAL tickets in the QENG Jira project!

The `scripts/` directory contains standalone test scripts that create actual Jira tickets. These scripts:
- Are **NOT** run by `pytest` or "run all tests"
- Require explicit confirmation before creating tickets
- Should only be run when specifically testing Jira integration

```powershell
# Comprehensive Jira service validation (creates tickets + updates)
python scripts/comprehensive_test.py

# Test workflow transitions (creates tickets + transitions through statuses)
python scripts/test_workflow_transitions.py

# Direct REST API test (creates tickets via raw API calls)
python scripts/test_create_direct.py
```

### Running Other Test Types

```powershell
# Run only integration tests
pytest -m integration

# Run all tests EXCEPT those that create Jira tickets (default)
pytest -m "not creates_jira_tickets"

# Run specific test file
pytest tests/test_system_locator.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Test Markers

The project uses these pytest markers:

- `@pytest.mark.creates_jira_tickets` - Tests that create real Jira tickets (excluded by default)
- `@pytest.mark.integration` - Integration tests that may hit external services
- `@pytest.mark.slow` - Tests that take a long time to run

## Configuration

Test behavior is configured in [pytest.ini](../pytest.ini):

```ini
# Default behavior: exclude Jira ticket-creating tests
addopts = -m "not creates_jira_tickets"
```

## Continuous Integration

In CI/CD pipelines, you should:

1. **Always exclude Jira ticket-creating tests** to avoid cluttering the project
2. Use environment variable checks to skip tests if credentials aren't available
3. Consider using a separate test Jira project for CI

Example CI command:
```bash
pytest -m "not creates_jira_tickets" --tb=short
```

## Safe Test Scripts

These scripts in `scripts/` are safe to run (read-only):

- `fetch_ticket.py` - Fetches existing ticket information
- `search_lab_requests.py` - Searches for tickets (no creation)
- `test_jira_auth.py` - Tests authentication only
- `check_transitions.py` - Checks available transitions (no modifications)
- `debug_tables.py` - Displays database information

## Best Practices

1. **Default behavior**: `pytest` excludes ticket creation
2. **Explicitly opt-in**: Use `-m creates_jira_tickets` when you want to test Jira integration
3. **Use descriptive summaries**: When creating test tickets, use summaries like "TEST: [description]"
4. **Clean up after yourself**: Consider deleting test tickets after validation
5. **Document in changelogs**: Note when you've created test tickets

## Environment Variables

Required for Jira integration tests:

```bash
JIRA_URL=https://your-jira-instance.com
JIRA_PAT=your_personal_access_token
JIRA_DEFAULT_ASSIGNEE=bbrice  # Optional, defaults to bbrice
```

## Troubleshooting

### "Unknown marker" error
If you see `PytestUnknownMarkWarning`, ensure [pytest.ini](../pytest.ini) exists in the project root.

### Tests still create Jira tickets
If running `pytest` creates tickets, check that:
1. [pytest.ini](../pytest.ini) exists and has the correct `addopts` setting
2. You're running pytest from the project root directory
3. You haven't overridden the `-m` flag in your command

### Authentication failures
- Verify `.env` file has correct `JIRA_URL` and `JIRA_PAT`
- Test auth with: `python scripts/test_jira_auth.py`
- Check PAT hasn't expired in Jira settings

## Adding New Tests

When adding tests that create Jira tickets:

```python
import pytest

@pytest.mark.creates_jira_tickets
def test_my_jira_integration(jira_client):
    """Test description.
    
    ⚠️ WARNING: This test creates a REAL Jira ticket!
    Run with: pytest -m creates_jira_tickets tests/test_file.py::test_my_jira_integration
    """
    # Test implementation
```

For standalone scripts:

```python
#!/usr/bin/env python3
"""Script description.

⚠️⚠️⚠️ WARNING: CREATES REAL JIRA TICKETS ⚠️⚠️⚠️

This script creates actual tickets in the QENG Jira project!
Only run this when you specifically want to test integration.

Usage:
    python scripts/my_test_script.py

NOTE: This script is NOT run by 'pytest' or 'run all tests'.
"""

def main():
    print("=" * 70)
    print("⚠️  MY TEST SCRIPT ⚠️")
    print("⚠️  CREATES REAL JIRA TICKETS ⚠️")
    print("=" * 70)
    
    response = input("\\nType 'yes' to continue: ")
    if response.lower() != 'yes':
        print("Aborted.")
        return 0
    
    # Test implementation
```
