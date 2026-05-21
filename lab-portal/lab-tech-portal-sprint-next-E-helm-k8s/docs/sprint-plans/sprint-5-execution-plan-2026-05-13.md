# Sprint 5 — Parallel Execution Plan

**Date:** 2026-05-13
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams --milestone Next`)
**Milestone / focus:** Next milestone — Sprint 5 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor concerns:** Slice C foundation (Celery + Redis + Jira resilience + JSON API skeleton) + Slice D-part1 SQLAlchemy spike
**Goal:** Lay the async task infrastructure that all Celery-dependent issues (#14, #15, #16, #17, #18) require. Ship JSON API skeleton to unblock OpenAPI docs and task-status API. Harden jira_service.py before Celery tasks inherit its brittleness.

---

## Pre-flight state

| Item | State | Notes |
|------|-------|-------|
| `master` tip | `3df4c67` | Sprint 4 merged: PR #76 (Prometheus metrics), PR #75 (skill infra) |
| Sprint 4 fully closed | done | #32, #52, #56, #57, #68 all closed |
| In-flight remote branches | 1 stale | `chore/add-jira-status-check-workflow` — 0 commits ahead of master, safe to ignore |
| `redis` / `celery` in requirements.txt | **NOT present** | Neither package installed yet |
| `celery_app.py` | **MISSING** | No Celery module exists |
| `api/` or `tools/api_v1/` blueprint | **MISSING** | Only inline `/api/v1/audit-log` in app.py |
| `services/jira_service.py` retry/rate-limit | **MISSING** | Plain `requests.Session()`, all field IDs hardcoded |
| `config.py` Redis/Celery keys | **DONE** | REDIS_URL, CELERY_BROKER_URL, etc. already present |
| `docker-compose.yml` Redis + worker + beat stubs | **DONE** | Services exist but worker/beat run stubs |
| `qe-check` CLI | **BLOCKED** | `ModuleNotFoundError: No module named 'adc_github_sdk'` — unresolved since Sprint 3 |

---

## Pre-flight AC Verification (Phase 0)

| Issue | Stated AC summary | Verified state | Classification |
|-------|-------------------|----------------|----------------|
| #12 — Redis broker setup | redis in requirements, config URLs, graceful degradation | config.py ✓, docker-compose ✓; requirements.txt and .env.example NOT done; no graceful degradation in app.py | **Partial** — proceed (2 files remain) |
| #13 — celery_app.py | celery_app.py, celery in requirements, Dockerfile worker CMD | celery_app.py MISSING; celery not in requirements; Dockerfile worker runs stub sleep | **Open** — proceed |
| #72 — jira_service.py hardening | HTTPAdapter retry, token-bucket, env-var field IDs | No retry, no rate limiter, all 6 field IDs hardcoded constants in class body | **Open** — proceed |
| #34 — global error handling | @app.errorhandler, error templates, structured JSON errors | Zero errorhandler decorators in app.py; no templates/errors/ directory | **Open** — proceed |
| #35 — JSON API skeleton | api_v1 blueprint at /api/v1/ | No api_v1 blueprint; only inline `/api/v1/audit-log` in app.py | **Open** — proceed |
| #45 — qe-check baseline | Baseline appended to guide-friction.md | qe-check crashes; no baseline heading in guide-friction.md | **Blocked** — adc_github_sdk still missing; excluded from wave |
| #48 — SQLAlchemy spike | tools/checkout/models.py, one read route migrated | tools/checkout/models.py MISSING; db.py uses raw sqlite3 | **Open** — Wave 2 |
| #14 — Jira print Celery tasks | tasks/print_request_tasks.py, form returns immediately | No tasks/ directory; no Celery dispatch in print_requests_app.py | **Open** — Wave 2 |
| #15 — Jira import Celery task | tasks/system_locator_tasks.py, async import | No tasks/ directory; import route fully synchronous | **Open** — Wave 2 |
| #16 — task status columns + API | jira_task_status/jira_task_id columns, /api/v1/tasks/<id>/status | db.py has jira_sync_error; jira_task_status and jira_task_id MISSING | **Open** — Wave 2 |
| #17 — Celery Beat | tasks/periodic.py, beat_schedule in celery_app.py | tasks/ MISSING; celery_app.py MISSING; depends on #13 | **Open** — Wave 2 |
| #18 — UI async feedback | Pending badge, polling, retry button | All Jira calls synchronous in templates; no polling JS | **Open** — Wave 3 |
| #53 — OpenAPI docs | /api/v1/docs, docs/api-spec.yaml, CI export | tools/api_v1/ MISSING; depends on #35 | **Open** — Wave 2 |

**Actionable Wave 1 issues (4):** #12+#13, #72, #34, #35
**Blocked (1):** #45 — excluded from wave
**Deferred to Wave 2 (7):** #48, #14, #15, #16, #17, #53 — depend on Wave 1 ships
**Deferred to Wave 3 (1):** #18 — depends on Wave 2 ships

---

## File Footprint Discovery (Phase 1)

### Issue #12 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `requirements.txt` | MODIFY | Add `redis` package |
| `.env.example` | MODIFY | Uncomment REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND from "Slice C NOT YET ACTIVE" block |
| `app.py` | MODIFY | Add graceful degradation startup check: ping Redis, log warning + continue if unavailable; add Redis check to `/readyz` probe |

### Issue #13 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `celery_app.py` | CREATE | `make_celery(app)` factory + `ContextTask` pattern; worker starts with `celery -A celery_app worker` |
| `requirements.txt` | MODIFY | Add `celery` (shared file with #12 — in same stream to avoid conflict) |
| `Dockerfile` | MODIFY | Replace stub `sleep` CMD in `worker` and `beat` stages with real `celery -A celery_app worker` and `celery -A celery_app beat` invocations |

### Issue #72 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `services/jira_service.py` | HEAVY_MODIFY | Mount `HTTPAdapter(max_retries=Retry(...))` on session; add token-bucket rate limiter class; move 6 hardcoded field IDs + issue type ID to `os.getenv()` reads; add `JiraRateLimitError` exception class |
| `config.py` | MODIFY | Add dataclass fields for `JIRA_CUSTOMFIELD_*` env vars and `JIRA_LAB_REQUEST_ISSUE_TYPE_ID` |
| `.env.example` | MODIFY | Activate commented-out `JIRA_CUSTOMFIELD_*` vars (lines 165-171) from "Slice C NOT YET ACTIVE" block |
| `tests/test_jira_service.py` | MODIFY | Add unit tests for retry behaviour (mock 429 → eventual success), rate limiter, env-var-driven field IDs; update assertion that hardcodes `customfield_18053` |

### Issue #34 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `app.py` | MODIFY | Add `@app.errorhandler(404)`, `@app.errorhandler(500)`, `@app.errorhandler(429)`, `@app.errorhandler(CSRFError)`; content-negotiate HTML vs JSON using `request.accept_mimetypes` or `/api/*` path prefix; inject `REQUEST_ID` from `request.environ` into error payloads |
| `templates/errors/404.html` | CREATE | User-friendly 404 page extending `base.html` |
| `templates/errors/500.html` | CREATE | User-friendly 500 page extending `base.html` |
| `tests/test_error_handlers.py` | CREATE | Tests: 404 returns HTML vs JSON by Accept header; 500 handler fires with request_id; CSRF error returns 400; 429 handled gracefully |

### Issue #35 file footprint (PRE-SPLIT — estimated L > 600 lines)
| Path | Change | Reason |
|------|--------|--------|
| `tools/api_v1/__init__.py` | CREATE | Package init for api_v1 blueprint |
| `tools/api_v1/api_v1_app.py` | HEAVY_MODIFY | Blueprint definition (`api_v1_bp`) + JSON endpoints for all 5 tools; migrate inline `/api/v1/audit-log` from app.py here |
| `app.py` | MODIFY | Remove inline `api_audit_log()` route; import and register `api_v1_bp` at `/api/v1/`; add `api_v1.*` to `require_login()` exemption or token-auth before_request; add CSRF exemption via `csrf.exempt(api_v1_bp)` |
| `tests/test_api_v1.py` | CREATE | Tests for all CRUD endpoints, status codes, input validation rejection, HTML routes still work |
| `tests/test_audit_log.py` | MODIFY | Verify `/api/v1/audit-log` still returns 200 after route moves to blueprint |

**Pre-split plan for #35:**
- **PR 1** (~350 lines): Blueprint scaffolding + `api_v1_app.py` skeleton + inventory + checkout JSON endpoints + `app.py` registration + audit-log migration
- **PR 2** (~350 lines): Print-requests + systems + rf-chambers JSON endpoints + `tests/test_api_v1.py` + input validation

---

## File Overlap Matrix (Phase 2)

### Wave 1 streams only

|          | Stream A (#12+#13) | Stream B (#72) | Stream C (#34) | Stream D (#35) |
|----------|--------------------|----------------|----------------|----------------|
| **A**    | —                  | 14% (`.env.example`) | 10% (`app.py`) | 10% (`app.py`) |
| **B**    |                    | —              | 0%             | 0%             |
| **C**    |                    |                | —              | 10% (`app.py`) |
| **D**    |                    |                |                | —              |

### Shared files — Wave 1

| File | Streams | Risk | Notes |
|------|---------|------|-------|
| `.env.example` | A, B | LOW | Stream A uncomments Redis section (lines ~162-178); Stream B uncomments Jira field section (lines ~165-171). Additive in different comment blocks — auto-merge expected |
| `app.py` | A, B, C, D | LOW-MEDIUM | Stream A: startup Redis ping (~5 lines near top); Stream C: error handlers (~30 lines near bottom); Stream D: blueprint registration + inline route removal (middle). All additive in different zones. Rebase as each merges. |

**No HIGH-risk shared files between any Wave 1 stream pair.** All overlaps are additive changes to different sections. Rebases are expected but should auto-resolve.

---

## Stream Formation (Phase 3)

### Stream A: Celery + Redis Foundation
- **Issues**: #12 (Partial), #13 (Open)
- **Why grouped**: Both touch `requirements.txt` — running in separate parallel streams would cause a merge conflict on that file. Dependencies are also sequential (#12 adds redis package that #13's Celery config depends on)
- **Total size**: S (combined ~80 lines)
- **Worktree**: `../lab-tech-portal-next-A-celery-redis`
- **Branch**: `feat/sprint-5-A-celery-redis`
- **Issue order**: #12 first (redis in requirements), then #13 (celery_app.py)
- **File footprint**: `requirements.txt`, `.env.example`, `app.py`, `celery_app.py`, `Dockerfile`

### Stream B: Jira Service Resilience
- **Issues**: #72 (Open)
- **Why singleton**: Touches `services/jira_service.py` which no other stream needs. Fully independent.
- **Total size**: M (~200 lines)
- **Worktree**: `../lab-tech-portal-next-B-jira-resilience`
- **Branch**: `feat/sprint-5-B-jira-resilience`
- **File footprint**: `services/jira_service.py`, `config.py`, `.env.example`, `tests/test_jira_service.py`

### Stream C: Global Error Handling
- **Issues**: #34 (Open)
- **Why singleton**: app.py changes (errorhandlers) in different section from Streams A and D. Error templates are net-new files.
- **Total size**: S (~80 lines + 2 new templates)
- **Worktree**: `../lab-tech-portal-next-C-error-handling`
- **Branch**: `feat/sprint-5-C-error-handling`
- **File footprint**: `app.py`, `templates/errors/404.html`, `templates/errors/500.html`, `tests/test_error_handlers.py`

### Stream D: JSON API Skeleton
- **Issues**: #35 (Open, PRE-SPLIT)
- **Why singleton**: Creates new `tools/api_v1/` package and modifies `app.py` blueprint registration. Large scope warrants a dedicated worktree.
- **Total size**: L → pre-split into 2 PRs
- **Worktree**: `../lab-tech-portal-next-D-json-api`
- **Branch**: `feat/sprint-5-D-json-api`
- **File footprint**: `tools/api_v1/__init__.py`, `tools/api_v1/api_v1_app.py`, `app.py`, `tests/test_api_v1.py`, `tests/test_audit_log.py`

---

## Dependency Graph

```
Wave 1 (all independent — start immediately)
───────────────────────────────────────────────────
Stream A (#12+#13)  ──┐
Stream B (#72)      ──┤
Stream C (#34)      ──┤  (no inter-dependencies)
Stream D (#35)      ──┘
[#45 BLOCKED — excluded from wave]

Wave 2 (after Wave 1 merges)
────────────────────────────────────────────────────────────────
Stream E (#17 Celery Beat)       ─── depends on: Stream A
Stream F (#48 SQLAlchemy spike)  ─── depends on: Stream A (soft: requirements.txt)
Stream G (#14+#15 Jira tasks)    ─── depends on: Streams A + B
Stream H (#16 task status)       ─── depends on: Streams A + D
Stream I (#53 OpenAPI docs)      ─── depends on: Stream D

Wave 3 (after Wave 2 merges)
────────────────────────────────────────────────────────────────
Stream J (#18 UI async feedback) ─── depends on: Streams G + H
```

---

## Agent Team Allocation (Phase 4)

| Stream | Issues | Classification | Dev Model | Est. Duration |
|--------|--------|----------------|-----------|---------------|
| A | #12 + #13 | Standard (small scope, existing patterns) | Sonnet | ~45 min |
| B | #72 | Standard (service hardening, well-defined) | Sonnet | ~90 min |
| C | #34 | Standard (errorhandlers, templates) | Sonnet | ~45 min |
| D | #35 | Complex (new blueprint system, L size) | Sonnet | ~2 h (2 PRs) |

**Wave 1 capacity:** 4 parallel Dev agents → ~2h total wall time (bottleneck: Stream D)

### Wave 2 allocation (for reference)

| Stream | Issues | Classification | Dev Model | Depends on |
|--------|--------|----------------|-----------|------------|
| E | #17 | Standard | Sonnet | Stream A merged |
| F | #48 | Standard (spike) | Sonnet | Stream A merged |
| G | #14+#15 | Complex (new tasks/ infra) | Sonnet | Streams A+B merged |
| H | #16 | Standard | Sonnet | Streams A+D merged |
| I | #53 | Standard | Sonnet | Stream D merged |

---

## Conflict-Cutting Rules

1. **Rebase daily**: `git fetch origin && git rebase origin/master` on every active worktree before pushing
2. **`app.py` soft edge**: Streams A, C, D all modify `app.py`. The first stream to merge will have no conflict. Subsequent streams must rebase and verify their section is still intact. Changes are in three non-overlapping zones (startup, error handlers, blueprint registration) — git auto-merge expected.
3. **`.env.example` soft edge**: Streams A and B both uncomment vars in `.env.example`. Different line ranges — auto-merge expected. If conflict, accept both sets of uncommented vars.
4. **PR titles** require `QENG-16846:` prefix and conventional commit scope
5. **Line budget**: 600 lines (additions + deletions) per PR. Stream D is pre-split into 2 PRs at ~350 lines each. If any stream approaches 600 lines, split before committing.
6. **One concern per PR** — no mixing unrelated concerns even within a stream
7. **Worktree cleanup**: `git worktree remove <path>` immediately after PR merge
8. **No Alembic migrations in Wave 1** — all Wave 1 streams use `_migrate_schema()` pattern or add no schema changes. Wave 2 Stream H (#16) adds columns via `_migrate_schema()` (no migration numbering conflict).

---

## Pre-flight checklist (run before spawning Wave 1 agents)

- [ ] `git checkout master && git pull` — clean tree on master
- [ ] Confirm `3df4c67` is still master tip (no surprise merges)
- [ ] Verify stale branch `chore/add-jira-status-check-workflow` does not overlap: `git diff origin/master...origin/chore/add-jira-status-check-workflow --name-only`
- [ ] Confirm Docker services healthy: `docker compose ps`
- [ ] Each Dev agent receives: stream row + issue bodies (from `gh issue view`) + this plan as context

---

## Status Tracking

### Wave 1

| Stream | Issues | Branch | PR | State | Depends on |
|--------|--------|--------|----|-------|------------|
| A | #12, #13 | `feat/sprint-5-A-celery-redis` | #85 | **merged** | — |
| B | #72 | `feat/sprint-5-B-jira-resilience` | #88 | **merged** | — |
| C | #34 | `feat/sprint-5-C-error-handling` | #86 | **merged** | — |
| D | #35 | `feat/sprint-5-D-json-api` | #87 | **merged** | — |

### Wave 2

| Stream | Issues | Branch | PR | State | Depends on |
|--------|--------|--------|----|-------|------------|
| E | #17 | `feat/sprint-5-E-celery-beat` | #96 | **merged** | Stream A |
| F | #48 | `feat/sprint-5-F-sqlalchemy-spike` | #94 | **merged** | Stream A |
| G | #14, #15 | `feat/sprint-5-G-celery-jira-tasks` | #97 | **merged** | Streams A + B |
| H | #16 | `feat/sprint-5-H-task-status` | #93 | **merged** | Streams A + D |
| I | #53 | `feat/sprint-5-I-openapi` | #95 | **merged** | Stream D |

### Wave 3

| Stream | Issues | Branch | PR | State | Depends on |
|--------|--------|--------|----|-------|------------|
| J | #18 | `feat/sprint-5-J-async-ui` | — | **in-progress** | Streams G + H |

### Blocked / Out-of-wave

| Issue | Reason | Resolution path |
|-------|--------|-----------------|
| #45 | `adc_github_sdk` not installed — qe-check crashes | Manually resolve: `pip install` from local qe-repo-ai-assisted-guide; then run `qe-check . --verbose` and append output to `docs/guide-friction.md` |

---

## Recommended next step

```
/sprint-kickoff --plan docs/sprint-plans/sprint-5-execution-plan-2026-05-13.md --wave 1
```

Or for full autonomous orchestration:

```
/wave-execute --plan docs/sprint-plans/sprint-5-execution-plan-2026-05-13.md --wave 1
```
