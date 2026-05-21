# Pull Request

## Summary

<!-- 2–4 bullet summary of what changed and why -->
-
-

## Linked issue(s)

Closes #<!-- issue number -->

## Slice

<!-- Which cleanup slice does this belong to? -->
`slice-` <!-- e.g. slice-0-baseline, slice-a-auth, slice-b-observability, slice-c-resilience, slice-d-part1, slice-g-part1 -->

## 5-Tool Coverage Matrix

> Required for all infrastructure / cross-cutting changes. For single-tool feature work, mark the other four N/A with a reason.

| Tool | Status | Notes |
|------|--------|-------|
| Inventory | `Applied` / `Done` / `N/A — <reason>` | |
| RF Chamber | `Applied` / `Done` / `N/A — <reason>` | |
| Equipment Checkout | `Applied` / `Done` / `N/A — <reason>` | |
| System Locator | `Applied` / `Done` / `N/A — <reason>` | |
| 3D Print Requests | `Applied` / `Done` / `N/A — <reason>` | |

## Test evidence

<!-- Paste curl output, screenshot, log line, or pytest summary demonstrating the new behavior -->
```
```

## Checklist

- [ ] PR title is `QENG-16846: type(scope): summary`
- [ ] `python -m pytest` passes (all existing tests green)
- [ ] ≥ 1 new test added (slice PRs: ≥ 5 new tests)
- [ ] No secrets hardcoded; `.env.example` updated if new vars introduced
- [ ] `init_db()` / `_ensure_db()` not called at module import time
- [ ] Pattern cited in new code: `# Pattern: docs/patterns/<cat>/<name>.md (qe-architecture-ai-assisted-guide @ <SHA>)` *(if adopting a guide pattern)*
- [ ] Guide-friction note appended to `docs/guide-friction.md` *(if a pattern doc was unclear or wrong)*
- [ ] Changelog entry committed: `docs: add changelog for YYYY-MM-DD`
- [ ] GitHub issue(s) will be closed on merge (reference above)
- [ ] Project #23 board updated (Priority + Size fields set)
