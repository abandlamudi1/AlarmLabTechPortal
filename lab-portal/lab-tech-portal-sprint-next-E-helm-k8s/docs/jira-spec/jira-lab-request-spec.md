# Jira Lab Request Ticket Specification

**Document Version:** 1.0  
**Last Updated:** February 6, 2026  
**Jira Instance:** https://jira.corp.adcinternal.com/jira  
**Project:** QENG (Quality Engineering)  
**Issue Type:** Lab Request

## Table of Contents
1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Issue Type Configuration](#issue-type-configuration)
4. [Custom Fields Reference](#custom-fields-reference)
5. [Workflow States & Transitions](#workflow-states--transitions)
6. [API Endpoints](#api-endpoints)
7. [Field Formats & Validation](#field-formats--validation)
8. [Example Operations](#example-operations)
9. [Common Pitfalls](#common-pitfalls)

---

## Overview

Lab Request tickets (issue type ID: 13901) are used in the QENG project to manage laboratory resource requests, hardware configuration, device troubleshooting, and lab setup activities. This specification documents all technical details required to programmatically create, update, and transition Lab Request tickets through their complete lifecycle.

**Key Characteristics:**
- **Project Key:** QENG
- **Issue Type:** Lab Request (ID: 13901)
- **Issue Type Name Caveat:** The display name is "Lab Request " with a trailing space, so always use the ID instead
- **Default Assignee:** bbrice (Benjamin Brice)
- **Base API Path:** /rest/api/2

---

## Authentication

### Method
**Bearer Token Authentication** using Personal Access Token (PAT)

### Headers Required
```http
Authorization: Bearer <PERSONAL_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json
```

### Environment Variables
```bash
JIRA_URL=https://jira.corp.adcinternal.com/jira
JIRA_PAT=<your_personal_access_token>
JIRA_DEFAULT_ASSIGNEE=bbrice  # Optional
```

### Authentication Validation Endpoint
```
GET /rest/api/2/myself
```

**Note:** Basic Authentication (username + password) is NOT supported. Only Bearer token with PAT works.

---

## Issue Type Configuration

### Issue Type Details
- **ID:** 13901
- **Name:** "Lab Request " (with trailing space)
- **Always use ID** in API calls to avoid name matching issues

### Project Details
- **Key:** QENG
- **Name:** Quality Engineering
- **ID:** (varies by instance)

---

## Custom Fields Reference

### Field Mappings

| Field Name | Field ID | Type | Required | Default Value |
|------------|----------|------|----------|---------------|
| Lab Request Type | customfield_18703 | Select (single choice) | No | None |
| Lead QE Team | customfield_16802 | Text | No | "Support Team" |
| Lead R&D Team | customfield_25100 | Text | No | "Quality Engineering" |
| Deadline | customfield_18053 | Date | No | None |
| Planned End Date | customfield_14636 | Date Picker | Yes (for In Progress) | None |
| High Level Estimate | customfield_19901 | Select (single choice) | Yes (for In Progress) | None |

### Standard Fields

| Field Name | Type | Required | Notes |
|------------|------|----------|-------|
| project | Object | Yes | `{"key": "QENG"}` |
| summary | String | Yes | Title of the ticket |
| description | String | No | Full description text |
| issuetype | Object | Yes | `{"id": "13901"}` |
| assignee | Object | No | `{"name": "username"}` or null for unassigned |
| priority | Object | No | `{"name": "High"}` (High, Medium, Low) |
| resolution | Object | Conditional | Required for Closed/Cancelled transitions |

### Lab Request Type Options
- None (null/empty)
- Hardware Configuration
- Device Wiring
- Device troubleshooting
- Lab setup
- Automation integration
- Other

**API Format:**
```json
{
  "customfield_18703": {"value": "Hardware Configuration"}
}
```

### High Level Estimate Options
- None (null/empty)
- X-Small
- Small
- Medium
- Large
- X-Large

**API Format:**
```json
{
  "customfield_19901": {"value": "Small"}
}
```

### Resolution Options
- Done
- Cancelled
- Won't Do
- Duplicate
- Cannot Reproduce
- Fixed Indirectly
- Expected Behavior
- Requires Follow Up
- Invalid
- No Response
- Declined
- Equipment Failure
- Software Error
- Automatically delayed

**API Format:**
```json
{
  "resolution": {"name": "Done"}
}
```

---

## Workflow States & Transitions

### Workflow States

```
[Defining Requirements] (default/initial state)
    ↓ ↑
    ↓ ↑ "Reopen"
    ↓ ↑
[On Hold] ←→ [Pending Staff] → [In Progress] → [Testing] → [Closed]
    ↓              ↑
    ↓              ↑ "Reopen"
    ↓              ↑
[Cancelled] ←------┘
```

### Detailed Transition Matrix

| From State | To State | Transition Name | Transition ID | Required Fields | Notes |
|------------|----------|-----------------|---------------|-----------------|-------|
| Defining Requirements | On Hold | "On Hold" | 131 | None | Pauses work |
| On Hold | Defining Requirements | "Reopen" | 71 | None | Resume planning |
| Defining Requirements | Pending Staff | "Request Help" | 111 | None | Waiting for lab staff |
| Pending Staff | Defining Requirements | "Defining Requirements" | 71 | None | Back to planning |
| Pending Staff | In Progress | "Start Progress" | 21 | Planned End Date, High Level Estimate | Begin work |
| In Progress | Testing | "Ready for Testing" | 121 | None | Ready for validation |
| Testing | Closed | "Closed" | 41 | Resolution (default: "Done") | Complete the ticket |
| Defining Requirements | Cancelled | "Cancelled" | 151 | Resolution (must be "Cancelled") | Cancel the request |
| Cancelled | Defining Requirements | "Reopen" | 71 | None | Reactivate cancelled ticket |
| Testing | In Progress | "In progress" | 191 | None | Return to development |
| Any State | On Hold | "On Hold" | 131 | None | Available from most states |

**Critical Discovery:** Transition names do NOT always match the destination status name. For example:
- To go to "Defining Requirements", use transition "Reopen"
- To go to "Pending Staff", use transition "Request Help"
- To go to "In Progress", use transition "Start Progress"
- To go to "Testing", use transition "Ready for Testing"

### Get Available Transitions
```http
GET /rest/api/2/issue/{issueKey}/transitions
```

**Response Example:**
```json
{
  "transitions": [
    {
      "id": "21",
      "name": "Start Progress",
      "to": {
        "id": "3",
        "name": "In Progress"
      }
    }
  ]
}
```

### Transition Requirements by State

#### In Progress (via "Start Progress")
**REQUIRED:**
- Planned End Date (customfield_14636): YYYY-MM-DD format
- High Level Estimate (customfield_19901): One of the valid options

**Example Payload:**
```json
{
  "transition": {"id": "21"},
  "fields": {
    "customfield_14636": "2026-03-01",
    "customfield_19901": {"value": "Small"}
  }
}
```

#### Closed (via "Closed")
**REQUIRED:**
- Resolution: Must specify a valid resolution option

**Example Payload:**
```json
{
  "transition": {"id": "41"},
  "fields": {
    "resolution": {"name": "Done"}
  }
}
```

#### Cancelled (via "Cancelled")
**REQUIRED:**
- Resolution: Must be set to "Cancelled"

**Example Payload:**
```json
{
  "transition": {"id": "151"},
  "fields": {
    "resolution": {"name": "Cancelled"}
  }
}
```

---

## API Endpoints

### Base URL
```
https://jira.corp.adcinternal.com/jira/rest/api/2
```

### Core Operations

#### Create Issue
```http
POST /rest/api/2/issue
```

#### Get Issue
```http
GET /rest/api/2/issue/{issueKey}
```

**Query Parameters:**
- `fields`: Comma-separated list or "*all"
- `expand`: Optional expansions (e.g., "changelog", "transitions")

#### Update Issue
```http
PUT /rest/api/2/issue/{issueKey}
```

#### Transition Issue
```http
POST /rest/api/2/issue/{issueKey}/transitions
```

#### Get Available Transitions
```http
GET /rest/api/2/issue/{issueKey}/transitions
```

#### Search for User
```http
GET /rest/api/2/user/search?username={query}
```

---

## Field Formats & Validation

### Date Fields

**Deadline & Planned End Date:**
- **Format:** YYYY-MM-DD
- **Type:** ISO 8601 date string
- **Example:** "2026-03-01"

**Incorrect formats that will fail:**
- d/MMM/yy (e.g., "1/Mar/26")
- MM/DD/YYYY (e.g., "03/01/2026")
- Unix timestamp

### Select Fields (Single Choice)

**Lab Request Type, High Level Estimate:**
```json
{
  "customfield_18703": {"value": "Hardware Configuration"}
}
```

**Important:** Use `{"value": "..."}` object format, not plain strings.

### Assignee Field

**Format:**
```json
{
  "assignee": {"name": "username"}
}
```

**Valid username formats:**
- Short username: "bbrice"
- Email: "user@example.com" (must exist in Jira)

**To unassign:**
```json
{
  "assignee": null
}
```

**Important:** Username "unassigned" does NOT exist - use null instead.

### Priority Field

**Format:**
```json
{
  "priority": {"name": "High"}
}
```

**Valid values:** High, Medium, Low (case-sensitive)

### Resolution Field

**Format:**
```json
{
  "resolution": {"name": "Done"}
}
```

**Important:** Set resolution DURING the transition, not before. Use the `fields` parameter in the transition API call.

---

## Example Operations

### Create Lab Request Ticket

```http
POST /rest/api/2/issue
Content-Type: application/json
Authorization: Bearer <token>

{
  "fields": {
    "project": {"key": "QENG"},
    "summary": "Configure new test device",
    "description": "Need to set up device XYZ for automated testing",
    "issuetype": {"id": "13901"},
    "assignee": {"name": "bbrice"},
    "priority": {"name": "High"},
    "customfield_18703": {"value": "Hardware Configuration"},
    "customfield_16802": "Support Team",
    "customfield_25100": "Quality Engineering",
    "customfield_18053": "2026-03-15"
  }
}
```

**Response:**
```json
{
  "id": "123456",
  "key": "QENG-16557",
  "self": "https://jira.corp.adcinternal.com/jira/rest/api/2/issue/123456"
}
```

### Update Issue Fields

```http
PUT /rest/api/2/issue/QENG-16557
Content-Type: application/json
Authorization: Bearer <token>

{
  "fields": {
    "description": "Updated description with more details",
    "assignee": {"name": "jdoe"},
    "customfield_18053": "2026-03-20"
  }
}
```

### Transition to In Progress

```http
POST /rest/api/2/issue/QENG-16557/transitions
Content-Type: application/json
Authorization: Bearer <token>

{
  "transition": {"id": "21"},
  "fields": {
    "customfield_14636": "2026-03-01",
    "customfield_19901": {"value": "Small"}
  },
  "update": {
    "comment": [
      {
        "add": {
          "body": "Starting work on this lab request"
        }
      }
    ]
  }
}
```

### Close Ticket

```http
POST /rest/api/2/issue/QENG-16557/transitions
Content-Type: application/json
Authorization: Bearer <token>

{
  "transition": {"id": "41"},
  "fields": {
    "resolution": {"name": "Done"}
  },
  "update": {
    "comment": [
      {
        "add": {
          "body": "Lab request completed successfully"
        }
      }
    ]
  }
}
```

### Get Issue with Specific Fields

```http
GET /rest/api/2/issue/QENG-16557?fields=summary,status,assignee,customfield_18703,customfield_14636,customfield_19901
Authorization: Bearer <token>
```

---

## Common Pitfalls

### 1. Issue Type Name with Trailing Space
**Problem:** Issue type name is "Lab Request " with trailing space  
**Solution:** Always use ID "13901" instead of name

```json
// ❌ DON'T
{"issuetype": {"name": "Lab Request"}}

// ✅ DO
{"issuetype": {"id": "13901"}}
```

### 2. Transition Name vs Status Name Mismatch
**Problem:** Transition names don't match destination status names  
**Solution:** Always fetch available transitions first or use documented transition names

```json
// ❌ DON'T assume transition name = status name
{"transition": {"name": "In Progress"}}

// ✅ DO use correct transition name
{"transition": {"name": "Start Progress"}}
```

### 3. Setting Resolution Before Transition
**Problem:** Setting resolution field before calling transition API  
**Solution:** Include resolution in the transition API call's fields parameter

```json
// ❌ DON'T update separately
PUT /issue/QENG-123 {"fields": {"resolution": {"name": "Done"}}}
POST /issue/QENG-123/transitions {"transition": {"id": "41"}}

// ✅ DO in single transition call
POST /issue/QENG-123/transitions {
  "transition": {"id": "41"},
  "fields": {"resolution": {"name": "Done"}}
}
```

### 4. Date Format Confusion
**Problem:** Using wrong date format (d/MMM/yy instead of YYYY-MM-DD)  
**Solution:** Always use ISO format YYYY-MM-DD

```json
// ❌ DON'T
{"customfield_14636": "1/Mar/26"}

// ✅ DO
{"customfield_14636": "2026-03-01"}
```

### 5. Unassigning Tickets
**Problem:** Using `{"assignee": {"name": "unassigned"}}`  
**Solution:** Use null to unassign

```json
// ❌ DON'T
{"assignee": {"name": "unassigned"}}

// ✅ DO
{"assignee": null}
```

### 6. Select Field Format
**Problem:** Passing string value directly instead of object  
**Solution:** Wrap in {"value": "..."} object

```json
// ❌ DON'T
{"customfield_18703": "Hardware Configuration"}

// ✅ DO
{"customfield_18703": {"value": "Hardware Configuration"}}
```

### 7. Missing Required Fields on Transition
**Problem:** Transitioning to In Progress without required fields  
**Solution:** Include Planned End Date and High Level Estimate in transition payload

```json
// ❌ DON'T
POST /transitions {"transition": {"id": "21"}}
// Will fail with 400 error

// ✅ DO
POST /transitions {
  "transition": {"id": "21"},
  "fields": {
    "customfield_14636": "2026-03-01",
    "customfield_19901": {"value": "Small"}
  }
}
```

### 8. Username Format
**Problem:** Using incorrect username format  
**Solution:** Use short username (e.g., "bbrice") not full name or wrong format

```json
// ❌ DON'T
{"assignee": {"name": "bbryce"}}  // Wrong spelling
{"assignee": {"name": "Benjamin Brice"}}  // Full name

// ✅ DO
{"assignee": {"name": "bbrice"}}  // Correct username
```

---

## Implementation Checklist

When implementing a Lab Request client in a new project:

- [ ] Set up Bearer token authentication with PAT
- [ ] Store credentials in environment variables (.env)
- [ ] Use issue type ID 13901, not name
- [ ] Map all 6 custom fields with correct field IDs
- [ ] Implement default values for Lead QE/R&D Teams
- [ ] Use YYYY-MM-DD format for all date fields
- [ ] Wrap select field values in {"value": "..."} objects
- [ ] Fetch available transitions before attempting transitions
- [ ] Validate required fields before In Progress transition
- [ ] Include resolution in Closed/Cancelled transition payloads
- [ ] Handle assignee as optional (null for unassigned)
- [ ] Test complete workflow: Create → Pending Staff → In Progress → Testing → Closed
- [ ] Validate transition names (not status names)
- [ ] Add error handling for 400 (missing required fields) and 401 (auth) errors

---

## Reference Implementation

See `/services/jira_service.py` in this repository for a complete Python implementation following this specification.

**Key methods:**
- `create_lab_request()`: Create with all fields
- `get_issue()`: Retrieve issue details
- `get_transitions()`: Fetch available transitions
- `transition_to_in_progress()`: With automatic required field handling
- `transition_to_closed()`: With resolution support
- Field-specific update methods for maintainability

**Test suite:**
- `/tests/test_jira_service.py`: Integration tests
- `/scripts/test_workflow_transitions.py`: Complete lifecycle validation

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-06 | Initial specification based on QENG Lab Request discovery |

---

## Contact & Support

For questions about this specification or Lab Request workflow:
- **Lab Staff Lead:** Benjamin Brice (bbrice)
- **Jira Instance:** https://jira.corp.adcinternal.com/jira
- **Project:** QENG (Quality Engineering)

