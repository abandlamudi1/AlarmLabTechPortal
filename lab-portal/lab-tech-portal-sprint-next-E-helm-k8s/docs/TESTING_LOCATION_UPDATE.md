# Location Model Update - Testing Guide

## Quick Test Summary

All tests passing ✓

- **Unit Tests**: 6/6 passed
- **Migration Test**: All scenarios passed
- **Database**: Schema and migration working correctly

---

## 1. Automated Tests (Recommended)

### Run All System Locator Tests
```bash
python -m pytest tests/test_system_locator.py -v
```

**Expected**: All 6 tests pass
- ✓ System creation and search flow
- ✓ Update and delete operations
- ✓ Search with no results
- ✓ Form validation (requires location_number and location_name)
- ✓ Duplicate identifier rejection
- ✓ Duplicate identifier rejection on edit

### Run Migration Verification
```bash
python scripts\test_location_migration.py
```

**Expected**: All 5 test scenarios pass confirming:
- New location fields (location_number, location_name) work correctly
- Legacy fields (building, room, sub_location) are NULL
- Create, read, update, delete operations work
- Search includes new location fields

### Run All Tests
```bash
python -m pytest tests/ -v
```

---

## 2. Manual Testing via Web UI

### Start the Flask Application
```bash
python app.py
```

Navigate to: http://127.0.0.1:5000

### Test Scenarios

#### A. Create New System
1. Go to **System Locator** → **Add System**
2. Fill in:
   - **System name**: Test System 1
   - **Location Number**: 10-640 *(required)*
   - **Location Name**: Automation Lab *(required)*
   - **Status**: Active
   - **Identifiers**: Add CID-TEST123
3. Click **Save**
4. **Expected**: Success message, redirects to dashboard showing new system

#### B. Search and View
1. Search for "10-640" in the search box
2. **Expected**: Shows systems at that location
3. Verify location is displayed as: `10-640 · Automation Lab`

#### C. Edit Existing System
1. Click on a system to edit
2. Update **Location Name** to: "Automation Lab - Updated"
3. **Expected**: Location updates successfully
4. Verify old fields (building, room, sub_location) are NOT visible in the form

#### D. Validation Testing
1. Try creating a system without Location Number
2. **Expected**: Error message "Location Number is required (e.g., 10-640)"
3. Try creating without Location Name
4. **Expected**: Error message "Location Name is required (e.g., Automation Lab)"

---

## 3. Database Verification

### Check Schema
```bash
python -c "import sqlite3; conn = sqlite3.connect('tools/system_locator/systems.db'); print([col[1] for col in conn.execute('PRAGMA table_info(systems)')])"
```

**Expected columns include**:
- location_number
- location_name
- building (legacy, should be NULL)
- room (legacy, should be NULL)
- sub_location (legacy, should be NULL)

### Verify Data Migration
```bash
python -c "import sqlite3; conn = sqlite3.connect('tools/system_locator/systems.db'); systems = conn.execute('SELECT name, location_number, location_name, building, room, sub_location FROM systems WHERE status != \"Decommissioned\"').fetchall(); print('Active Systems:'); [print(f'  {s[0]}: {s[1]} · {s[2]} (legacy: {s[3]}/{s[4]}/{s[5]})') for s in systems]"
```

**Expected**: Active systems show location_number and location_name, legacy fields are NULL

---

## 4. Jira Import Testing

### Test Description Parser
```bash
python -c "from tools.system_locator.description_parser import DescriptionParser; result = DescriptionParser.extract_location('10-640- Test System', '# 10 Floor'); print(f'location_number: {result[\"location_number\"]}'); print(f'location_name: {result[\"location_name\"]}')"
```

**Expected**:
- location_number: 10-640
- location_name: Floor 10

### Test Jira Import Service
```bash
python scripts/test_import_service.py
```

**Expected**: Import service processes location fields correctly

---

## 5. API/Endpoint Testing

### Create System via POST
```powershell
$body = @{
    name = "API Test System"
    location_number = "10-999"
    location_name = "API Test Lab"
    status = "Active"
    identifier_label = @("CID")
    identifier_value = @("API-TEST")
}
```

---

## 6. Edge Cases to Test

### ✓ Empty Database
- Start with fresh database
- Migration should add columns
- Create first system with new fields

### ✓ Existing Data
- If you have existing systems with building/room data
- Run migration to convert to location_number
- Verify: `building="10" + room="640"` becomes `location_number="10-640"`

### ✓ Mixed Data
- Systems with only building, only room, or both
- Migration handles all cases gracefully

---

## What Changed

### Database (db.py)
- ✅ Building, room, sub_location set to NULL in all new operations
- ✅ Migration converts existing data automatically
- ✅ Location number and location name are now the primary fields

### Application (system_locator_app.py)
- ✅ Removed legacy fields from form payloads
- ✅ Validation enforces location_number and location_name
- ✅ Display uses new fields only

### Parser (description_parser.py)
- ✅ Extracts location_number from Jira ticket format (e.g., "10-640-")
- ✅ Extracts location_name from floor mentions
- ✅ Returns only new fields (no legacy)

### Import Service (jira_import_service.py)
- ✅ Maps location_number and location_name from Jira fields
- ✅ Removed legacy field mappings
- ✅ Creates systems with new location model

### Templates (system_form.html)
- ✅ Shows only Location Number and Location Name
- ✅ Includes helpful placeholders ("10-640", "Automation Lab")
- ✅ No building/room/sub-location fields visible

---

## Success Criteria

All of the following should be true:

- ✅ All pytest tests pass
- ✅ Can create systems with location_number and location_name
- ✅ Validation prevents empty location fields
- ✅ Web UI shows new location format: "10-640 · Automation Lab"
- ✅ Legacy fields (building, room, sub_location) are NULL in database
- ✅ Migration runs without errors
- ✅ Search works with new location fields
- ✅ Jira import uses new location model

---

## Rollback (If Needed)

The database columns still exist (building, room, sub_location), so rolling back code changes alone would work. However, new data won't have those fields populated since they're set to NULL.

To fully rollback:
1. Revert code changes
2. Run a script to split location_number back to building/room if needed
3. Restore backups if available

---

## Next Steps

1. ✅ Run automated tests: `python -m pytest tests/test_system_locator.py -v`
2. ✅ Run migration test: `python scripts\test_location_migration.py`
3. 🔍 Manual testing via web UI (optional but recommended)
4. 📊 Check any existing systems display correctly
5. 📝 Update end-of-day changelog with these changes
