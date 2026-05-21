# Changelog - 2026-02-12

**Contributor**: Ben_Brice  
**Branch**: master  
**Commits**: [commit hash] to [commit hash]

---

## 📝 Summary

Configured test suite to prevent accidental Jira ticket creation and cleaned up 22 test tickets from previous testing sessions.

---

## 🔧 Changes Made

### What Changed
- ✅ Created `pytest.ini` with custom marker `@pytest.mark.creates_jira_tickets`
- ✅ Configured pytest to automatically exclude Jira ticket-creating tests from default runs  
- ✅ Marked 2 tests in `tests/test_jira_service.py` that create real Jira tickets
- ✅ Added warning banners and confirmation prompts to 3 standalone test scripts
- ✅ Created comprehensive testing documentation (`docs/TESTING_GUIDE.md`, `docs/JIRA_TEST_CONFIG_SUMMARY.md`)
- ✅ Updated `README.md` with testing instructions
- ✅ Created `scripts/cancel_test_tickets.py` to bulk-cancel test tickets
- ✅ Cancelled all 22 test tickets (QENG-16450 through QENG-16585)

### Why These Changes
**Problem**: Discovered many test Jira tickets being created by testing scripts during development. These cluttered the project board and weren't clearly marked as test data.

**Solution Approach**:
1. **Pytest markers**: Used pytest's marker system to tag ticket-creating tests
2. **Default exclusion**: Configured pytest.ini to exclude these by default - "run all tests" now means "run all SAFE tests"
3. **Explicit opt-in**: Tests that create tickets require explicit flag: `pytest -m creates_jira_tickets`
4. **Script protection**: Added confirmation prompts to standalone scripts that create tickets
5. **Documentation**: Created comprehensive guides so future developers understand the system

**Technical Decision**: Fixed Jira transition issue by passing resolution field as part of transition payload rather than separate update.

---

## 🧪 Testing & Validation

### Commands to Reproduce
```powershell
# Run all safe tests (automatically excludes Jira ticket creation) - 31 tests pass
python -m pytest

# Show which tests are excluded
python -m pytest --collect-only -q
# Output: collected 33 items / 2 deselected / 31 selected

# Explicitly run Jira ticket-creating tests (2 tests)
pytest -m creates_jira_tickets

# Check available pytest markers
python -m pytest --markers
```

### What to Look For
- ✅ Default `pytest` command runs 31 tests, deselects 2
- ✅ Standalone scripts require typing "yes" to proceed
- ✅ Test tickets show "Cancelled" status with AI Agent comment

---

## 🚨 Breaking Changes / Important Notes

**Behavior Change**: Running `pytest` now excludes tests that create real Jira tickets by default. This is intentional and improves safety.

**To run ticket-creating tests**: Use `pytest -m creates_jira_tickets` explicitly.

---

## ❓ Open Questions / Discussion Needed

- None - system working as designed

---

## 📚 Documentation Updates

- ✅ Created `docs/TESTING_GUIDE.md` - Comprehensive testing instructions
- ✅ Created `docs/JIRA_TEST_CONFIG_SUMMARY.md` - Quick reference for test configuration
- ✅ Updated `README.md` - Added testing section with warning about Jira tests

---

## 🔗 Related Issues / PRs

- Addresses issue of test ticket clutter in QENG project
- Prevents future accidental test ticket creation during development

---

## 💡 Next Steps / Tomorrow's Tasks

1. Monitor pytest configuration in team workflows
2. Consider adding CI/CD check to ensure safe tests only
3. Document in onboarding that test tickets are excluded by default

---

## 🐛 Bugs Fixed / Issues Resolved

- Fixed: Jira transition to "Cancelled" was failing with resolution field error
  - **Root cause**: Resolution field must be passed as part of transition payload, not as separate update
  - **Solution**: Updated transition call to include `fields={"resolution": {"name": "Cancelled"}}`
- Cleaned up: 22 test Jira tickets (QENG-16450, QENG-16555, QENG-16558, QENG-16563-16573, QENG-16577-16585)

---

## 📊 Metrics / Performance

- Test suite: 31 safe tests, 2 Jira integration tests (excluded by default)
- Successfully cancelled: 22/22 test tickets
- Files created: 7 (pytest.ini, 2 docs, 4 scripts)
- Files modified: 5 (tests, scripts, README)

---

## 🗒️ Additional Notes

**Key Learnings**:
1. Pytest markers are powerful for test categorization and selective execution
2. Jira workflow transitions have field requirements that vary by workflow state
3. Resolution field on "Cancelled" transition must be in payload, not pre-set
4. Good defaults (exclude risky tests) + explicit opt-in = safer development workflow

**Scripts Created**:
- `scripts/cancel_test_tickets.py` - Bulk cancel test tickets with confirmation
- `scripts/check_available_transitions.py` - Debug available transitions for tickets
- `scripts/test_single_cancel.py` - Test single ticket cancellation
