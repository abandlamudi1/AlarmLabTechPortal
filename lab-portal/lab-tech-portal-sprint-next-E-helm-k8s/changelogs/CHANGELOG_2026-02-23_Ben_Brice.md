# Changelog - 2026-02-23

**Contributor**: Ben_Brice  
**Branch**: master  
**Commits**: [commit hash] to [commit hash]

---

## 📝 Summary

Expanded 3D print requests to support Jira creation, status tracking, attachments, and richer detail/history views while keeping standard tests safe from ticket creation.

---

## 🔧 Changes Made

### What Changed
- Added request detail and history pages with attachment downloads and inline design image previews.
- Added print status dropdown (Design/Printing/Cancelled/Closed) and removed closed/cancelled items from the active queue.
- Implemented immediate Jira ticket creation on submit with attachment upload and error visibility.
- Added Jira transition handling for Cancelled/Closed when transition IDs are configured.
- Stored `uploaded_image_path`, `print_status`, and `jira_sync_error` in the print requests database.
- Refined upload UX: image always optional; file optional for new design; both shown for upload-file and new-design types.
- Defaulted Jira deadline to the request due date, or two weeks from request creation if blank.
- Added Jira creation feature flag to keep standard pytest runs from creating tickets.
- Added Jira-only test for 3D print requests, plus unit tests for detail view, status flow, and default deadline.
- Updated documentation for new fields, Jira sync behavior, and testing commands.

### Why These Changes
Provide a complete 3D print request workflow with Jira integration, better visibility, and safer testing defaults.

---

## 🧪 Testing & Validation

### Commands to Reproduce
```bash
python -m pytest
```

### What to Look For
- Requests create Jira tickets with attachments when credentials are configured.
- Status updates archive requests and optionally transition Jira tickets.
- Detail pages show full metadata and inline design image previews.

---

## 🚨 Breaking Changes / Important Notes

- None.

---

## ❓ Open Questions / Discussion Needed

- None.

---

## 📚 Documentation Updates

- Updated README.md with the new `uploaded_image_path` field and Jira sync behavior.

---

## 🔗 Related Issues / PRs

- None.

---

## 💡 Next Steps / Tomorrow's Tasks

1. Add optional UI guidance text if users need help attaching reference images.

---

## 🐛 Bugs Fixed / Issues Resolved

- None.

---

## 📊 Metrics / Performance

- Tests: 36 passed, 2 deselected.

---

## 🗒️ Additional Notes

- Design images are stored under `tools/print_requests/uploads/design_images`.
- Jira creation is disabled during standard pytest runs; use `pytest -m creates_jira_tickets` for Jira tests.

---

## Update - 2026-02-23 12:31

**Quick Summary**: Expanded 3D print request workflow with Jira creation, status tracking, detail/history views, and safer test handling.

### Notes
- Tests: `python -m pytest`

