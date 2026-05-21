# Sprint 3 — Wave 3 Execution Plan

**Date:** 2026-05-13
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams`)
**Sprint:** Sprint 3 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Wave:** 3 (final Sprint 3 wave)
**Anchor slices:** Slice B completion (audit log + RBAC enforcement) + Infra housekeeping (Compose profiles + Dockerfile test target)
**Goal:** Close Sprint 3 by landing the two Slice B follow-ups that Wave 2 deferred, plus two small infra improvements.

---

## Pre-flight state

| Item | State | Notes |
|---|---|---|
| `master` tip | `567edc9` | Wave 2 merged: PR #61 (Slice B observability), PR #62 (Slice D-part1 data layer) |
| 7 issues closed via Wave 2 | done | #7, #33, #2, #3, #9, #24, #47 |
| `services/rbac.py` | warn-only mode | `RBAC_ENFORCEMENT_MODE` defaults to `warn-only`; enforce path exists but gated |
| `services/audit_log.py` | **does not exist** | #46 creates it; rbac.py's docstring already cites this dependency |
| `docker-compose.yml` | redis/worker/beat defined, no `profiles:` | Services present from PR #58; `profiles: [worker]` missing — worker/beat start by default |
| `Dockerfile` | multi-stage (builder/base/web/worker/beat), no `test` stage | Comment on line 35 defers test-target split to "a later slice" |
| `requirements.txt` | `pytest==9.0.2` included in flat list | Must move to a test-only install to benefit from the Dockerfile test target split |

---

## Pre-flight AC verification (Phase 0)

| Issue | Stated AC summary | Verified state | Classification |
|-------|-------------------|----------------|----------------|
| #46 — Audit log table | `services/audit_log.py`, 5-tool emit calls, `/api/v1/audit-log` | No audit infrastructure exists; `rbac.py` has `NOTE: audit-logging.md` pattern citation (forward ref only) | **Open** — proceed as written |
| #63 — RBAC enforcement flip | `check_permission()` raises 403; `TODO(Slice-B)` removed | `rbac.py` confirmed warn-only (6 occurrences of `warn-only`); enforce path is code-complete but gated | **Open** — depends on #46 |
| #64 — Compose profiles | `profiles: [worker]` on worker + beat; `docker compose up` starts only web | redis/worker/beat services present; **zero `profiles:` keys** — worker + beat currently start by default | **Open** (partial: services exist, profiles key missing) |
| #65 — Dockerfile test target | `test` stage in Dockerfile; CI uses `--target test` | Multi-stage (builder/base/web/worker/beat) exists; **no `test` stage**; CI builds web target only | **Open** (partial: infrastructure ready, test stage missing) |

**No issues are Shipped.** All four proceed.

**Surprises captured:**
- `docker-compose.yml` already has redis/worker/beat (from PR #58) — #64's scope reduces to adding `profiles: [worker]` on worker + beat (2-line YAML change + 1 new doc file).
- `Dockerfile` already has a multi-stage builder — #65 scope is adding a `test` stage + removing pytest from requirements.txt + updating CI.
- `rbac.py` enforce path is already code-complete (`abort(403)` is there, gated by `RBAC_ENFORCEMENT_MODE == "enforce"`). #63 only needs to: flip the default, remove the warn-only escape, update tests.

---

## Stream definitions

### Stream A — Slice B completion
- **Issues:** #46 (audit log table + 5-tool wiring), #63 (RBAC enforcement flip)
- **Internal order:** #46 first → #63 second (#63 imports `audit_log.log_event()` on denial path)
- **Branch:** `feature/sprint-3-slice-b-completion`
- **Worktree:** `../lab-tech-portal-sprint-3-slice-b-completion`
- **Size:** M (~500–650 lines; #46 is the bulk, #63 is ~100 lines)
- **Model:** Sonnet (security-sensitive new service, 5-tool wiring, behavior change in auth path)
- **File footprint:**
  - `services/audit_log.py` (NEW — `log_event(actor, action, resource_type, resource_id, detail)`, SQLite at `DATA_DIR/db/audit.db`)
  - `app.py` (add `/api/v1/audit-log` read-only admin-only endpoint)
  - `config.py` (add `AUDIT_LOG_DB_PATH` env override)
  - `tools/system_locator/system_locator_app.py` (add emit calls: hard-delete, create/edit)
  - `tools/print_requests/print_requests_app.py` (add emit calls: status change, Jira sync)
  - `tools/checkout/checkout_app.py` (add emit calls: check-out, return)
  - `tools/inventory/inventory_app.py` (add emit calls: quantity adjustment)
  - `tools/rf_chamber/rf_chamber_app.py` (add emit calls: chamber edit, reservation change)
  - `services/rbac.py` (flip default to `enforce`; call `audit_log.log_event()` on denial; remove warn-only escape; remove `TODO(Slice-B)` comment)
  - `tests/test_audit_log.py` (NEW — ≥5 tests: event creation, retrieval, DB path override)
  - `tests/test_rbac.py` (MODIFY — existing warn-only pass-through tests → assert 403)
  - `tests/test_rbac_enforce.py` (NEW — enforce path for at least one tool endpoint)
- **Pattern citation:** `# Pattern: docs/patterns/observability/audit-logging.md` + `# Pattern: docs/patterns/auth/multi-mode-auth.md`
- **Guide-friction:** Add entry if audit-logging.md doesn't address SQLite-per-service vs. shared audit DB choice

### Stream B — Infra housekeeping
- **Issues:** #65 (Dockerfile test target split), #64 (Compose profiles)
- **Internal order:** #65 first (Dockerfile + requirements + CI) → #64 second (docker-compose.yml YAML change + doc)
- **Branch:** `feature/sprint-3-infra-housekeeping`
- **Worktree:** `../lab-tech-portal-sprint-3-infra-housekeeping`
- **Size:** S (~80–150 lines)
- **Model:** Sonnet (CI workflow changes require judgment on caching strategy)
- **File footprint:**
  - `Dockerfile` (add `test` stage: `FROM base AS test` + `RUN pip install pytest==9.0.2`; remove test-dep comment)
  - `requirements.txt` (remove `pytest==9.0.2` — it moves to the test stage's direct pip install)
  - `.github/workflows/ci.yml` (add `build test` step using `--target test`; run pytest inside test container)
  - `docker-compose.yml` (add `profiles: [worker]` to worker and beat services)
  - `docs/workflows/docker-compose-profiles.md` (NEW — one-liner: `docker compose --profile worker up`)

---

## File-overlap matrix

| | Stream A (Slice B) | Stream B (Infra) |
|---|---|---|
| Stream A | — | **zero overlap** |
| Stream B | | — |

**Shared files: none.** Stream A is 100% Python code (`services/`, `tools/`, `app.py`, `tests/`). Stream B is 100% infra (`Dockerfile`, `requirements.txt`, `.github/workflows/`, `docker-compose.yml`, `docs/`). These streams are fully parallel with zero rebase conflict risk.

---

## Dependency graph

```
Wave 2 (merged) ──► Both Wave 3 streams unblocked
                      │
                      ├──► Stream A (audit log + RBAC enforce) ─┐
                      │    (internal: #46 → #63)                │
                      │                                         ├──► Wave 3 merges
                      └──► Stream B (Dockerfile + Compose) ─────┘
                                                                │
                                                                ▼
                                                        Sprint 3 complete
```

---

## Agent team allocation

| Stream | Dev agent model | Rationale |
|--------|-----------------|-----------|
| A — Slice B completion | **Sonnet** | New `audit_log.py` service; 5-tool emit wiring; security-sensitive RBAC behavior change; judgment needed on audit event schema. |
| B — Infra housekeeping | **Sonnet** | CI workflow changes (Docker Buildx caching, test target pipeline) require judgment to avoid breaking the cache key strategy. |

---

## Line-budget enforcement

Default: **one PR per stream**. Only split if diff exceeds 1500 lines of mixed concerns.

**Pre-split prediction:** Stream A is ~500–650 lines and concentrated in well-separated files (service, 5 tool files, tests). No split expected. Stream B is ~80–150 lines. No split.

---

## Conflict-cutting rules (inherited)

1. **Rebase daily:** `git fetch origin && git rebase origin/master` on every active worktree.
2. **One concern per PR** (or pre-split per above).
3. **PR titles** require `QENG-16846:` prefix and conventional commit form.
4. **5-tool coverage matrix** in Stream A's PR (audit emit + RBAC verify for all 5 tools).
5. **Pattern citation** in new code where applicable: `# Pattern: docs/patterns/<area>/<file>.md`.
6. **Guide-friction:** any pattern ambiguity → entry in `docs/guide-friction.md`.
7. **Worktree cleanup**: `/sprint-close <PR#>` after merge handles it.
8. **`Refs` vs `Closes`** in PR bodies: `Closes #N` only for issues that are fully resolved in the PR. Stream A closes #46 and #63; Stream B closes #64 and #65.

---

## Status tracking

| Stream | State | Branch | PR | Depends on | Blockers |
|--------|-------|--------|----|-|----------|
| A — Slice B completion | **in-progress** | `feature/sprint-3-slice-b-completion` | — | — | none |
| B — Infra housekeeping | **in-progress** | `feature/sprint-3-infra-housekeeping` | #67 | — | none |

---

## Pre-flight checklist (run once before spawning agents)

- [ ] `git checkout master && git pull` — confirm at `567edc9`, clean tree
- [ ] Confirm Wave 2 PRs (#61, #62) both merged and worktrees removed (`git worktree list`)
- [ ] No in-flight branches touching `services/`, `tools/`, `Dockerfile`, or `docker-compose.yml`
- [ ] Stream A brief includes: `services/audit_log.py` schema, 5-tool event table, RBAC enforce path
- [ ] Stream B brief includes: requirements.txt pytest removal strategy, CI cache-key preservation

---

## DoD per stream

**Stream A — opens PR when:**
- [ ] `python -m pytest` passes (existing + new tests for audit log + RBAC enforcement)
- [ ] `services/audit_log.py` exists with `log_event()` signature matching issue #46
- [ ] All 5 tool apps emit audit events for the listed operations
- [ ] `GET /api/v1/audit-log` returns 200 for admin, 403 for lab-tech
- [ ] `services/rbac.py` raises 403 on role mismatch (warn-only escape removed)
- [ ] `TODO(Slice-B)` comment in `rbac.py` removed
- [ ] 5-tool coverage matrix in PR description
- [ ] Issues #46 and #63 close on PR merge

**Stream B — opens PR when:**
- [ ] `docker build --target web .` succeeds, image size ≤ pre-PR baseline
- [ ] `docker build --target test .` succeeds, `pytest` is importable in test stage
- [ ] CI pipeline runs `--target test` for the pytest step
- [ ] `docker compose up` (no profile) starts web + redis only (worker/beat gated)
- [ ] `docker compose --profile worker up` starts web + redis + worker + beat
- [ ] `docs/workflows/docker-compose-profiles.md` exists with usage note
- [ ] Issues #64 and #65 close on PR merge

---

## Capacity plan

| Wave | Streams | Parallel agents | Est. wall-clock | Bottleneck |
|------|---------|-----------------|-----------------|------------|
| 3    | 2       | 2 Dev (Sonnet)  | ~1 session      | Stream A (5-tool wiring) |

---

## Next step (Sprint 4)

Wave 3 closes Sprint 3. Sprint 4 scope (from sprint-3 plan §Next step):
- **Slice C:** Celery + Redis + JSON API skeleton
- **SQLAlchemy spike:** #48 Equipment Checkout ORM layer (de-risks Slice D-part2)

Plan via `/plan-parallel-streams` at Sprint 4 kickoff.
