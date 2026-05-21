# Jira Test Configuration Summary

## ✅ What Was Done

### 1. Created pytest.ini Configuration
- Added custom marker: `@pytest.mark.creates_jira_tickets`
- Default behavior: Automatically excludes tests that create real Jira tickets
- Location: [pytest.ini](../pytest.ini)

### 2. Marked Pytest Tests
Updated [tests/test_jira_service.py](../tests/test_jira_service.py) with markers:
- `test_create_lab_request_integration` - Creates a test Lab Request
- `test_update_methods_integration` - Creates and updates a test Lab Request

Updated [tests/test_print_requests_jira.py](../tests/test_print_requests_jira.py) with marker:
- `test_print_request_creates_jira_ticket` - Creates a test 3D print request Jira ticket

These tests are now excluded from default `pytest` runs.

### 3. Added Warnings to Standalone Scripts
Added prominent warnings and confirmation prompts to:
- [scripts/comprehensive_test.py](../scripts/comprehensive_test.py)
- [scripts/test_workflow_transitions.py](../scripts/test_workflow_transitions.py)
- [scripts/test_create_direct.py](../scripts/test_create_direct.py)

Each script now:
- Has a warning banner in the docstring
- Displays a warning before execution
- Requires typing "yes" to proceed
- Is NOT run by pytest

### 4. Created Documentation
- [docs/TESTING_GUIDE.md](../docs/TESTING_GUIDE.md) - Comprehensive testing guide
- Updated [README.md](../README.md) - Added reference to testing guide

## 📝 Usage Examples

### Default: Run All Safe Tests
```powershell
# Runs 31 tests, excludes 2 ticket-creating tests
python -m pytest
```

### Run Jira Ticket-Creating Tests
```powershell
# Run all Jira ticket-creating tests (3 tests)
pytest -m creates_jira_tickets

# Run a specific Jira test
pytest -m creates_jira_tickets tests/test_jira_service.py::test_create_lab_request_integration

# Run with verbose output
pytest -m creates_jira_tickets -v
```

### Run Standalone Scripts (Requires Confirmation)
```powershell
# Each script will prompt for confirmation
python scripts/comprehensive_test.py
python scripts/test_workflow_transitions.py
python scripts/test_create_direct.py
```

## 🔍 Verification

Test collection shows proper filtering:
```
# Default run
collected 33 items / 2 deselected / 31 selected

# With -m creates_jira_tickets
collected 33 items / 31 deselected / 2 selected
```

## Safe Scripts in scripts/

These scripts are read-only and safe to run anytime:
- `fetch_ticket.py` - Read ticket data
- `search_lab_requests.py` - Search tickets
- `test_jira_auth.py` - Test authentication only
- `check_transitions.py` - Check available transitions
- `debug_tables.py` - Display database info

## 📊 Test Summary

| Command | Tests Run | Creates Jira Tickets? |
|---------|-----------|----------------------|
| `pytest` | 31 | ❌ No |
| `pytest -m creates_jira_tickets` | 3 | ⚠️ Yes |
| `python scripts/comprehensive_test.py` | N/A | ⚠️ Yes (after confirmation) |
| `python scripts/test_workflow_transitions.py` | N/A | ⚠️ Yes (after confirmation) |
| `python scripts/test_create_direct.py` | N/A | ⚠️ Yes (after confirmation) |

## Next Steps

1. **Default workflow**: Just run `pytest` - it automatically excludes ticket creation
2. **When testing Jira integration**: Use `pytest -m creates_jira_tickets`
3. **For comprehensive Jira validation**: Run individual scripts when needed
4. **Update daily workflows**: Consider adding `pytest` to your daily routine (see [scripts/daily-routine/](../scripts/daily-routine/))
5. **CI/CD**: Use `pytest -m "not creates_jira_tickets"` (already the default)

## Files Modified

- ✅ [pytest.ini](../pytest.ini) - Created with markers and default exclusion
- ✅ [tests/test_jira_service.py](../tests/test_jira_service.py) - Added markers to 2 tests
- ✅ [scripts/comprehensive_test.py](../scripts/comprehensive_test.py) - Added warnings
- ✅ [scripts/test_workflow_transitions.py](../scripts/test_workflow_transitions.py) - Added warnings
- ✅ [scripts/test_create_direct.py](../scripts/test_create_direct.py) - Added warnings
- ✅ [docs/TESTING_GUIDE.md](../docs/TESTING_GUIDE.md) - Created comprehensive guide
- ✅ [README.md](../README.md) - Updated testing section
