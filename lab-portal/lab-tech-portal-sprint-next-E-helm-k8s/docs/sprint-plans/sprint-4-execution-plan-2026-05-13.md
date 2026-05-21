# Sprint 4 — Parallel Execution Plan

**Date:** 2026-05-13
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams --milestone Now`)
**Milestone / focus:** Now milestone — Sprint 4 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor concerns:** Skill infrastructure build-out (handoff skill, guide-friction-sync) + observability foundation (Prometheus /metrics endpoint)
**Goal:** Ship the automation tooling that the guide-friction-sync workflow depends on, and pull forward Prometheus metrics so Slice C has visibility.

---

## Pre-flight state

| Item | State | Notes |
|------|-------|-------|
| `master` tip | `657c7b8` | Wave 3 merged: PR #69 (Slice B completion), PR #67 (Infra housekeeping) |
| Sprint 3 fully closed | done | Wave 3 PRs #67 and #69 merged; worktrees removed |
| `/guide-friction-sync` SKILL.md | `DRAFT / SKETCH v0` | Design complete 2026-05-12; orchestration code, smoke tests, sprint-close wiring unbuilt |
| `/handoff` skill | does not exist | `.claude/skills/handoff/` directory absent; AGENTS.md still has manual handoff prose |
| `/metrics` endpoint | does not exist | No prometheus-flask-exporter in requirements.txt; no services/metrics.py |
| `qe-check` CLI | **BLOCKED** | `ModuleNotFoundError: No module named 'adc_github_sdk'` — same blocker as Sprint 3 |
| `/api/v1/` blueprints | do not exist | Slice C (Next milestone) is prerequisite |

---

## Pre-flight AC Verification (Phase 0)

Sub-agent footprinting on all 8 Now-milestone issues against current `master`:

| Issue | Stated AC summary | Verified state | Classification |
|-------|-------------------|----------------|----------------|
| #68 — fix doc relative links | Links resolve from `docs/skill-development/` | Grep confirms broken: `sprint-plans/...` (missing `../` prefix) in wave-execute-skill-handoff doc | **Open** — proceed |
| #57 — /handoff skill | SKILL.md, AGENTS.md reference, optional Stop hook | No `.claude/skills/handoff/` directory; AGENTS.md §Sprint/Task Execution has manual prose only | **Open** — proceed |
| #56 — guide-friction-sync build | Smoke test green, DRAFT header removed, sprint-close wired | SKILL.md line 4 still `DRAFT / SKETCH v0`; 7 promotion tasks unmet; sprint-close/SKILL.md has no --no-pr phase | **Open** — proceed |
| #54 — qe-check green | All three checkers pass | Depends on #53 (OpenAPI) which depends on Slice C JSON API skeleton — blocked upstream | **Blocked** — defer |
| #53 — OpenAPI docs | `/api/v1/docs` serving Swagger UI | No Python files in `/api/v1/`; issue body explicitly depends on #35 (Slice C, Next milestone) | **Blocked** — recommend moving to Next milestone |
| #52 — guide-improvement PRs | ≥4 PRs opened against guide repos | No `in-pr`/`merged` entries in guide-friction.md; issue body notes superseded by #56 once #56 lands | **Superseded** — close when #56 merges |
| #45 — qe-check baseline | Baseline output appended to guide-friction.md | `qe-check` crashes with `ModuleNotFoundError: No module named 'adc_github_sdk'` — same blocker as Sprint 3 | **Blocked** — adc_github_sdk still missing |
| #32 — Prometheus metrics | `/metrics` endpoint, custom business metrics, Grafana template | No prometheus-flask-exporter in requirements.txt; no /metrics route; no services/metrics.py | **Open** — proceed |

**Actionable issues (4):** #68, #57, #56, #32
**Blocked / deferred (4):** #53 (move to Next), #54 (blocked on #53), #45 (adc_github_sdk), #52 (superseded by #56)

**Stop condition check:** Not all issues are Shipped — proceeding with the 4 open issues.

---

## File Footprint Discovery (Phase 1)

### Issue #68 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `docs/skill-development/wave-execute-skill-handoff-2026-05-13.md` | MODIFY | Fix 3 broken relative links: `sprint-plans/...` → `../sprint-plans/...` and `skill-development/...` self-reference → `./wave-execute-skill-handoff-2026-05-13.md` |

### Issue #57 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `.claude/skills/handoff/SKILL.md` | CREATE | New skill — directory absent |
| `AGENTS.md` | MODIFY | §Sprint/Task Execution (lines 36-41): replace manual handoff prose with /handoff invocation reference |
| `.claude/settings.json` | MODIFY | Add `Stop` hook entry invoking `/handoff` when context warnings appear (issue ACs include optional hook wiring) |
| `docs/guide-friction.md` | MODIFY | Add F06 friction entry proposing context-budget transition pattern to qe-architecture-ai-assisted-guide |

### Issue #56 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `.claude/skills/guide-friction-sync/SKILL.md` | HEAVY_MODIFY | Remove DRAFT header; implement Phase 0–5; add reconciliation pass; document field-create first-run behavior |
| `.claude/skills/sprint-close/SKILL.md` | MODIFY | Add Phase 8 (or end-of-Phase-7 step) invoking `/guide-friction-sync --no-pr`; update argument-hint frontmatter with `--no-pr` |
| `AGENTS.md` | MODIFY | §Issue Hygiene (lines 42-48): add reference to /guide-friction-sync as canonical implementation |
| `docs/guide-friction.md` | MODIFY | Smoke-test run updates F01/F03 statuses; lifecycle diagram deposited into "How to use this file" section |

### Issue #32 file footprint
| Path | Change | Reason |
|------|--------|--------|
| `requirements.txt` | MODIFY | Add `prometheus-flask-exporter` and `prometheus-client` |
| `services/metrics.py` | CREATE | `init_app(app)` pattern; all custom Gauge/Counter/Histogram metrics declared |
| `app.py` | HEAVY_MODIFY | `metrics.init_app(app)` call; add `"metrics"` to auth-exemption set (same pattern as `"healthz"`, `"readyz"`); login/logout hooks for active-session gauge |
| `config.py` | MODIFY | Add `METRICS_ENABLED` (bool, default True) and `METRICS_NAMESPACE` (str) config fields |
| `services/jira_service.py` | MODIFY | Wrap Jira call sites with `jira_task_success_total` / `jira_task_failure_total` counter increments |
| `tests/test_metrics.py` | CREATE | Verify `/metrics` returns 200 without auth; correct Content-Type; custom metric names present; `METRICS_ENABLED=False` suppresses endpoint |
| `tests/conftest.py` | MODIFY | Add `METRICS_ENABLED=False` to app fixture config block (prevent prometheus state accumulation across tests) |
| `docs/grafana/lab-tech-portal-dashboard.json` | CREATE | Grafana dashboard template per AC; panels for HTTP rate/latency, Jira task rates, active sessions |
| `docker-compose.yml` | MODIFY | Add `prometheus` service with volume-mounted scrape config; add optional `grafana` service |
| `docs/prometheus.yml` | CREATE | Prometheus scrape config targeting `web:PORT/metrics` at 15s interval |

**Implementation scope notes for #32:**
- **Active sessions**: cookie-based sessions have no server-side store yet — gauge tracks login/logout hooks and resets on restart. Accepted limitation, documented in service.
- **Celery queue depth**: declared in `services/metrics.py` with stub return (0) until Slice C ships `celery_app.py`. Do not block on Celery.
- **DB query latency**: probe-level only via `_check_db()` in `app.py`. Wrapping all 5 tool `db.py` files is scope-creep into Slice D-part2; defer.

---

## File Overlap Analysis (Phase 2)

### Shared files across ALL four issues

| File | Issues | Risk |
|------|--------|------|
| `AGENTS.md` | #57 (§Sprint/Task Execution, lines 36-41), #56 (§Issue Hygiene, lines 42-48) | **HIGH — adjacent sections (one blank line apart at line 41-42); naive diff produces conflict** |
| `docs/guide-friction.md` | #57 (append F06 entry), #56 (update F01/F03 statuses + deposit lifecycle diagram) | MEDIUM — different regions but same file |

### File overlap matrix (Jaccard-like, % of smaller footprint)

|       | #68 | #57 | #56 | #32 |
|-------|-----|-----|-----|-----|
| **#68** | — | 0% | 0% | 0% |
| **#57** | | — | 50%¹ | 0% |
| **#56** | | | — | 0% |
| **#32** | | | | — |

¹ 2 shared files (AGENTS.md + guide-friction.md) / min(4, 4) = 50%. Both are **SOFT EDGES** but AGENTS.md is HIGH risk due to adjacent sections.

### Decision: Group #68 + #57 + #56 into a single stream

The AGENTS.md adjacent-section conflict (#57 modifies lines 36-41, #56 modifies lines 42-48) is HIGH risk in separate worktrees. All three issues (#68, #57, #56) are pure skill/docs work with no Python code. Grouping them into a single stream allows AGENTS.md to be updated once in a coordinated pass, eliminating the conflict entirely.

**Issue #32 has zero overlap with the skill/docs stream** — full parallelism is preserved.

---

## Stream Definitions (Phase 3)

### Stream A — Skill Infrastructure
- **Issues:** #68 (doc link fix), #57 (/handoff skill), #56 (guide-friction-sync build)
- **Why grouped:** AGENTS.md adjacent-section HIGH conflict risk; all pure skill/docs work; natural single PR
- **Internal order:** #68 first (trivial, 2-min) → #57 (design /handoff SKILL.md) → #56 (build guide-friction-sync orchestration + sprint-close wiring) → AGENTS.md both sections in one pass → guide-friction.md combined update
- **Branch:** `feat/sprint-4-skill-infra`
- **Worktree:** `../lab-tech-portal-sprint-4-skill-infra`
- **SP estimate:** ~8 (L — large SKILL.md rewrite + new handoff skill + settings.json + docs fix)
- **Est. diff:** ~450–550 lines
- **File footprint (unique across issues):**
  - `docs/skill-development/wave-execute-skill-handoff-2026-05-13.md` (MODIFY)
  - `.claude/skills/handoff/SKILL.md` (CREATE)
  - `.claude/settings.json` (MODIFY)
  - `AGENTS.md` (MODIFY — both §Sprint/Task Execution and §Issue Hygiene in one pass)
  - `docs/guide-friction.md` (MODIFY)
  - `.claude/skills/guide-friction-sync/SKILL.md` (HEAVY_MODIFY)
  - `.claude/skills/sprint-close/SKILL.md` (MODIFY)
- **Closes on merge:** #68, #57, #56, and #52 (superseded — close with comment referencing #56's PR)

### Stream B — Prometheus Metrics
- **Issues:** #32 (/metrics endpoint + custom business metrics + Grafana template)
- **Why singleton:** Zero overlap with Stream A; entirely different concern area (Python/Flask/observability)
- **Internal order:** `requirements.txt` first → `services/metrics.py` → `config.py` → `app.py` → `services/jira_service.py` → `tests/` → `docker-compose.yml` + `docs/prometheus.yml` → Grafana template
- **Branch:** `feat/sprint-4-prometheus-metrics`
- **Worktree:** `../lab-tech-portal-sprint-4-prometheus`
- **SP estimate:** ~5 (M)
- **Est. diff:** ~520 lines (per sub-agent estimate)
- **File footprint:**
  - `requirements.txt`
  - `services/metrics.py` (CREATE)
  - `app.py` (HEAVY_MODIFY)
  - `config.py`
  - `services/jira_service.py`
  - `tests/test_metrics.py` (CREATE)
  - `tests/conftest.py`
  - `docs/grafana/lab-tech-portal-dashboard.json` (CREATE)
  - `docker-compose.yml`
  - `docs/prometheus.yml` (CREATE)
- **Closes on merge:** #32

---

## File-Overlap Verification (Wave 1)

| Stream A footprint | Stream B footprint | Overlap? |
|--------------------|-------------------|---------|
| `docs/skill-development/...` | — | ✅ none |
| `.claude/skills/handoff/SKILL.md` | — | ✅ none |
| `.claude/settings.json` | — | ✅ none |
| `AGENTS.md` | — | ✅ none |
| `docs/guide-friction.md` | — | ✅ none |
| `.claude/skills/guide-friction-sync/SKILL.md` | — | ✅ none |
| `.claude/skills/sprint-close/SKILL.md` | — | ✅ none |
| — | `requirements.txt` | ✅ none |
| — | `services/metrics.py` | ✅ none |
| — | `app.py` | ✅ none |
| — | `config.py` | ✅ none |
| — | `services/jira_service.py` | ✅ none |
| — | `tests/test_metrics.py` | ✅ none |
| — | `tests/conftest.py` | ✅ none |
| — | `docs/grafana/*.json` | ✅ none |
| — | `docker-compose.yml` | ✅ none |
| — | `docs/prometheus.yml` | ✅ none |

**Zero file overlap between Wave 1 streams. Full parallelism with zero rebase-conflict risk.**

---

## Dependency Graph

```
Sprint 3 (merged) ──► Both Wave 1 streams unblocked
                       │
                       ├──► Stream A (skill infra: #68, #57, #56) ─┐
                       │    Internal: #68 → #57 → #56             │
                       │                                           ├──► Sprint 4 complete
                       └──► Stream B (Prometheus: #32) ───────────┘

Blocked (not in wave):
  #45 (qe-check baseline) ── blocked: adc_github_sdk missing
  #53 (OpenAPI docs) ──────── blocked: depends on Slice C (#35, Next milestone)
  #54 (qe-check green) ─────── blocked: depends on #53
  #52 (guide PRs manual) ──── superseded by #56; closes when Stream A merges
```

---

## Agent Team Allocation

| Stream | Dev model | Rationale |
|--------|-----------|-----------|
| A — Skill Infrastructure | **Sonnet** | SKILL.md design requires system-design judgment; /handoff skill architecture; orchestration phases for guide-friction-sync |
| B — Prometheus Metrics | **Sonnet** | Flask middleware integration; custom metric design; auth-exemption path; Grafana dashboard JSON; docker-compose Prometheus topology |

---

## Line-Budget Enforcement

Default (per wave-execute decision #5): **one PR per stream; only split if >1500 lines mixed concerns.**

| Stream | Estimated lines | Split needed? |
|--------|----------------|---------------|
| A — Skill Infrastructure | ~450–550 | No (single concern: skill/docs) |
| B — Prometheus Metrics | ~520 | No (single concern: observability) |

---

## Conflict-Cutting Rules (inherited)

1. **Rebase daily:** `git fetch origin && git rebase origin/master` on every active worktree.
2. **Migration check before branching:** `ls backend/migrations/versions/ 2>/dev/null | tail -1` — no migrations in scope for either stream.
3. **One concern per PR** — enforced by grouping strategy above.
4. **PR titles** require `QENG-16846:` prefix and conventional commit form.
5. **5-tool coverage matrix** in Stream B's PR description (metrics.py touches jira_service but not all 5 tool apps — coverage note: audit-log counters deferred to Slice C when Celery is live).
6. **Pattern citation** in new code: `# Pattern: docs/patterns/observability/audit-logging.md` in services/metrics.py.
7. **Guide-friction entry**: any pattern ambiguity → entry in `docs/guide-friction.md`.
8. **Worktree cleanup**: `/sprint-close <PR#>` after each merge.
9. **`Closes #N`** in PR body for fully resolved issues. `Refs #N` for partial.

---

## Status Tracking

| Stream | State | Branch | PR | Depends on | Blockers |
|--------|-------|--------|----|------------|----------|
| A — Skill Infrastructure | **merged** | `feat/sprint-4-skill-infra` | #75 | — | none |
| B — Prometheus Metrics | **merged** | `feat/sprint-4-prometheus-metrics` | #76 | — | none |

---

## Deferred Issues (not in this wave)

| Issue | Reason | Recommended action |
|-------|--------|--------------------|
| #45 — qe-check baseline | `qe-check` CLI crashes: `ModuleNotFoundError: No module named 'adc_github_sdk'` | Install adc_github_sdk in local guide env; re-evaluate for Sprint 5 |
| #53 — OpenAPI docs | Depends on #35 JSON API skeleton (Next milestone, Slice C) | Move issue milestone from Now → Next |
| #54 — qe-check green | Depends on #53; cannot proceed until Slice C lands | Move to Icebox or Next pending #53 |
| #52 — guide-improvement PRs (manual) | Superseded by #56 | Close with comment "Superseded by #56 — /guide-friction-sync automates this" when Stream A merges |

---

## Pre-flight Checklist (run once before spawning agents)

- [ ] `git checkout master && git pull` — confirm at `657c7b8`, clean tree
- [ ] Confirm no in-flight worktrees: `git worktree list`
- [ ] No in-flight branches touching `app.py`, `.claude/skills/`, `AGENTS.md`: `gh pr list --repo adc-quality/lab-tech-portal --state open`
- [ ] Stream A agent brief includes: existing guide-friction-sync SKILL.md content, AGENTS.md lines 36-48, wave-execute handoff doc's broken links (3 specific paths), sprint-close SKILL.md Phase 7 anchor for --no-pr wiring
- [ ] Stream B agent brief includes: app.py lines 290-310 (require_login auth-exemption set), conftest.py fixture block, jira_service.py call sites for counter wiring, CONTAINERIZATION_ROADMAP §4.6
- [ ] Docker services healthy: `docker compose ps`

---

## DoD per Stream

**Stream A — opens PR when:**
- [ ] `docs/skill-development/wave-execute-skill-handoff-2026-05-13.md` links resolve correctly from `docs/skill-development/` path (fixes #68)
- [ ] `.claude/skills/handoff/SKILL.md` exists and covers: auto-pulled context, AskUserQuestion interview, output path, "what to read first" format (meets #57 SKILL.md draft AC)
- [ ] `AGENTS.md` §Sprint/Task Execution references `/handoff` as canonical implementation
- [ ] `.claude/skills/guide-friction-sync/SKILL.md` `DRAFT / SKETCH v0` header removed; all 5 phases (0–5) have implementation prose (not just design notes)
- [ ] `.claude/skills/sprint-close/SKILL.md` has a --no-pr step invoking /guide-friction-sync
- [ ] `AGENTS.md` §Issue Hygiene references /guide-friction-sync
- [ ] Issues #68, #57, #56 `Closes` in PR body; #52 `Closes` with superseded note

**Stream B — opens PR when:**
- [ ] `GET /metrics` returns 200 without session cookie (auth-exempt)
- [ ] Response Content-Type is `text/plain; version=0.0.4; charset=utf-8` (Prometheus exposition format)
- [ ] Custom metric names present in output: `lab_portal_jira_task_success_total`, `lab_portal_jira_task_failure_total`, `lab_portal_active_user_sessions`, `lab_portal_db_query_duration_seconds`
- [ ] `METRICS_ENABLED=False` in config suppresses the endpoint
- [ ] `docker compose up` (without profile) includes prometheus service in the topology
- [ ] `docs/grafana/lab-tech-portal-dashboard.json` exists with ≥4 panels
- [ ] `python -m pytest tests/test_metrics.py` passes
- [ ] Issue #32 `Closes` in PR body

---

## Capacity Plan

| Wave | Streams | Parallel agents | Est. wall-clock | Bottleneck |
|------|---------|-----------------|-----------------|------------|
| 1    | 2       | 2 Dev (Sonnet)  | ~1 session      | Stream A (~550 lines of skill design) |

---

## Next Step (Sprint 5)

Sprint 4 closes the skill infrastructure gap and adds Prometheus observability. Sprint 5 scope:
- **Slice C:** Celery + Redis + JSON API skeleton (#12, #13, #14, #15, #16, #18, #35, #72)
- **SQLAlchemy spike:** #48 Equipment Checkout ORM layer (de-risks Slice D-part2)
- **Unblock #53 → #54 → #45** once Slice C JSON API skeleton (#35) is in master

Plan via `/plan-parallel-streams --milestone Next` at Sprint 5 kickoff.
