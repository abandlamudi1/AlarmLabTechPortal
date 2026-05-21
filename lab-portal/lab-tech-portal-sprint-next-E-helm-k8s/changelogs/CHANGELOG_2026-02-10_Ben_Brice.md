# Changelog - 2026-02-10

**Contributor**: Ben_Brice  
**Branch**: master  
**Commits**: [To be filled after commit]

---

## 📝 Summary

Enhanced System Locator with HQ location enforcement, bidirectional auto-fill, terminology updates ("System" → "System Profile"), and added PIN-protected hard delete functionality.

---

## 🔧 Changes Made

### What Changed
- [x] Renamed "System" to "System Profile" throughout user-facing text (UI, messages, tests)
- [x] Implemented HQ location mapping (10 locations) as source of truth
- [x] Added bidirectional auto-fill: Location Number ↔ Location Name
- [x] Added server-side location validation with clear error messages
- [x] Special handling for Panels Team Lab (no location number required)
- [x] Added PIN-protected hard delete functionality (PIN: 9420)
- [x] Created modal UI for delete confirmation with password input
- [x] Added `hard_delete_system()` in db.py for permanent deletion
- [x] Updated all tests to use valid HQ locations and new terminology

### Why These Changes
- **Terminology**: "System Profile" better describes what these records represent (profiles of physical systems)
- **HQ Location Map**: Prevents invalid location data entry, ensures consistency across all system profiles
- **Bidirectional Auto-fill**: Reduces data entry errors and improves UX by auto-populating the complementary field
- **PIN-protected Delete**: Provides temporary safeguard for permanent deletion until proper authentication is implemented
- **Server-side Validation**: Ensures data integrity even if client-side validation is bypassed

---

## 🧪 Testing & Validation

### Commands to Reproduce
```bash
# Run all tests (33 tests, all passing)
python -m pytest tests/ -v

# Run System Locator tests specifically
python -m pytest tests/test_system_locator.py -v

# Run PIN-protected delete tests
python -m pytest tests/test_pin_protected_delete.py -v

# Start the app and test manually
python app.py
# Navigate to http://localhost:5000/systems
# Try creating/editing a System Profile with different locations
# Try the PIN-protected delete (PIN: 9420)
```
**PIN for Hard Delete**: The PIN for permanently deleting System Profiles is **9420**. This is a temporary measure until proper authentication is implemented. Do NOT share this publicly.

**Location Validation**: Any existing system profiles with invalid locations (not in HQ location map) will fail validation on edit. The 10 valid HQ locations are:
- 10-640 → Automation Lab
- 10-510 → QE Lab  
- 10-630 → Product Testing Lab
- 10-070 → Hardware Test Framework Lab
- 11-050 → DE Lab
- 9-070 → International Lab
- 7-370 → Commercial Team Lab
- 6-430 → Mobile/CX Team Lab
- 5-030 → Video Team Lab
- (none) → Panels Team Lab

---

## ❓ Open Questions / Discussion Needed

- [ ] Should we add a configuration file for the HQ location map to make it easier to update locations without code changes?
- [ ] Should PIN be moved to environment variable instead of hardcoded?
- [ ] Do we need an audit log for hard deletions?

---

## 📚 Documentation Updates

- [x] Added inline code comments for location validation logic
- [x] Updated test files with new terminology and valid locations
- [x] Copilot instructions already document the daily workflow

---

## 🔗 Related Issues / PRs

- Related to System Locator enhancement initiative
- Addresses team feedback on location data consistency

---

## 💡 Next Steps / Tomorrow's Tasks

1. Consider moving PIN to environment variable for better security
2. Monitor for any existing system profiles with invalid locations
3. Consider adding audit log for hard delete operations
4. Future: Replace PIN system with proper authentication

---

## 🐛 Bugs Fixed / Issues Resolved

- Fixed terminology inconsistency (using both "System" and "System Profile")
- Resolved location data validation gaps (previously no validation on location fields)
- Fixed Jira import tests that used legacy building/room/sub_location fields
- Related work: [link to related changelogs or docs]

---

## 💡 Next Steps / Tomorrow's Tasks

1. [Task to pick up tomorrow]
2. [Follow-up needed]
3. [Future improvements to consider]

- **Test coverage**: 33 tests passing (added 4 new tests for PIN-protected delete)
- **Files modified**: 
  - `tools/system_locator/system_locator_app.py` - Added location mapping, validation, auto-populate logic, PIN-protected route
  - `tools/system_locator/db.py` - Added `hard_delete_system()` function
  - `tools/system_locator/templates/system_form.html` - Added dropdowns, modal UI, JavaScript auto-fill
  - `tools/system_locator/templates/systems_dashboard.html` - Terminology updates
  - `tools/system_locator/templates/jira_import.html` - Terminology updates
  - `tests/test_system_locator.py` - Updated with new terminology and valid locations
  - `tests/test_jira_import_service.py` - Updated to use location_number/location_name
  - `tests/test_pin_protected_delete.py` - New test file (4 tests)
- **Lines added**: ~400+ (including modal HTML, CSS, JavaScript)
- **Database**: No schema changes required (leverages existing location_number/location_name fields)
- Resolved: [Description of bug and fix]

---

## 📊 Metrics / Performance

[If applicable, note any performance improvements, test coverage changes, etc.]

- Test coverage: X%
- Performance: [Before/After metrics]
- Lines changed: [+additions/-deletions]

---

## 🗒️ Additional Notes

[Any other context, learnings, or notes worth documenting]
