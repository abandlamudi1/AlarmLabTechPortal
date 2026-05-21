# Sprint 6 — Parallel Execution Plan

**Date:** 2026-05-14
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams --milestone Next`)
**Milestone / focus:** Next milestone — Sprint 6 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor concerns:** Skill infra hardening (Sprint 5 friction backlog) + Slice C follow-ups (Redis health, Celery tuning, Jira pre-flight) + Slice H closure prep (UI design system gap)
**Goal:** Drain the skill-infrastructure backlog (#77–84) that has accumulated since Sprint 3 wave-execute friction, close out Sprint 5 Wave 2/3 Copilot-surfaced follow-ups (#89, #90, #99, #100), and stand up the design system foundation work (#103) that closes the Wave 3 carry-forward.

**Sprint capacity target:** 20–30 story points | Target waves: 2 | Target streams/wave: 5–8
**Actual scoped:** 13 issues, estimated ~21 story points across 8 streams (7 Wave 1 + 1 Wave 2)
**Excluded with reason:** #45 (qe-check baseline) blocked by missing `adc_github_sdk` dependency since Sprint 3 — same blocker as Sprint 5. #105 (under-load detection) already shipped in Sprint 5 Wave 3 — to be closed during pre-flight.

---

## Pre-flight state

| Item | State | Notes |
|------|-------|-------|
| `master` tip | `996b4d6` | Sprint 5 fully merged: PR #102 (Stream J async UI), PR #106 (Wave 3 close + AGENTS.md XSS rule) |
| Sprint 5 fully closed | ✅ done | All 12 Sprint 5 issues closed; Wave 1+2+3 plan-status table shows `merged` for every stream |
| Stale local branches | 1 | `docs/sprint-5-wave-3-close` (just merged via PR #106) — to be removed at kickoff |
| Safety tag | `pre-sync-recovery-2026-05-14` | Created during the squash-merge divergence cleanup; safe to delete |
| `adc_github_sdk` | **MISSING** | Same blocker as Sprint 5 — `qe-check` CLI installed in venv but Python import fails. **#45 stays blocked.** |
| `.claude/skills/skill-config.yml` | **MISSING** | #77 target file — does not exist |
| `services/health.py` | **MISSING** | `/readyz` lives inline in `app.py` (line 298). #89 modifies `app.py` directly |
| `tasks/` directory | ✅ present | `__init__.py`, `periodic.py`, `print_request_tasks.py`, `system_locator_tasks.py` — #99 + #100 target files exist |
| Slice G-part1 issues | **MISSING** | Wave 3 summary referenced ~6 Slice G-part1 Docker foundations issues; none exist in backlog. Recommend backlog grooming during Sprint 6 to populate Sprint 7. |

---

## Pre-flight AC Verification (Phase 0)

Verified by grep against `master` (commit `996b4d6`):

| Issue | Stated AC summary | Verified state | Classification |
|-------|-------------------|----------------|----------------|
| **#105** — wave-execute under-load detection | Step 0.3.5 added to `wave-execute/SKILL.md` | `Step 0.3.5 — Under-load check` exists at SKILL.md:73 | **Shipped** — close at kickoff |
| #77 — shared skill-config.yml | `.claude/skills/skill-config.yml` + all 13 SKILL.md reference `$CONFIG` | File does not exist; no SKILL.md references `$CONFIG` | **Open** — proceed |
| #78 — sprint-close project #26 → #23 | `projectV2(number: 23)` in sprint-close/SKILL.md | Still uses `projectV2(number: 26)` at lines 151, 160 | **Open** — proceed |
| #79 — wave-execute Phase 3 in-progress update | Explicit Edit-tool step before commit | Passing mention at SKILL.md:214 ("Also update…") but no explicit step | **Partial** — proceed (scope: add explicit step + example diff) |
| #80 — wave-execute `--include-untracked` | Phase 0.6 stash uses `--include-untracked` | Step 0.6 exists at SKILL.md:127; `--include-untracked` flag NOT present | **Open** — proceed |
| #81 — wave-execute `--batch` in Phase 5 | Phase 5 summary suggests `/sprint-close --batch …` | Phase 5 exists (SKILL.md:355) but does not mention `--batch` | **Open** — proceed |
| #82 — wave-execute stale-worktree detection | Phase 0 detects already-merged worktrees | No `git worktree list` check in Phase 0 | **Open** — proceed |
| #83 — sprint-close PR-modified-friction trigger | Trigger fires when merged PR touched `docs/guide-friction.md` | Only triggers on slice-label exhaustion (SKILL.md:320, 347) | **Open** — proceed |
| #84 — plan-parallel-streams Wave column | Status table has `Wave` column | Capacity table at line 414 has Wave column; status table at Step 5.1 does not | **Open** — proceed |
| #89 — Redis health in `/readyz` | `redis` key in `checks` map; 503 on unreachable | No redis check in `app.py:298-onwards` `/readyz` route | **Open** — proceed |
| #90 — Celery worker production tuning | Dockerfile + compose + config tuning flags | Dockerfile has only `--loglevel=info` (line 93, 100); no tuning env vars in docker-compose.yml or config.py | **Open** — proceed |
| #99 — print-requests dead code | `upload_jira_attachment` dispatched OR removed | Function still defined in `tasks/print_request_tasks.py`; never dispatched | **Open** — proceed |
| #100 — system-locator Jira pre-flight | `_validate_jira_connectivity()` call before async dispatch | `tools/system_locator/system_locator_app.py:512` dispatches without pre-flight | **Open** — proceed |
| #103 — UI design system guide gap | Architecture guide pattern + portal a11y audit | Neither exists | **Open** — proceed (scope updated 2026-05-14 to reference FW design system foundations as source of truth) |
| #45 — qe-check baseline | `qe-check` run + baseline appended to guide-friction.md | `qe-check` CLI installed but `adc_github_sdk` import fails | **Blocked** — excluded from Sprint 6 (same as Sprint 5) |

**Actionable Sprint 6 issues (13):** #77, #78, #79, #80, #81, #82, #83, #84, #89, #90, #99, #100, #103
**Shipped (1):** #105 — close at kickoff
**Blocked (1):** #45 — excluded; unblock first (file new issue against adc-quality/qe-repo-ai-assisted-guide if not already tracked)

---

## File Footprint Discovery (Phase 1)

### Skill-infrastructure issues — predictable footprints

| Issue | Path | Change | Reason |
|-------|------|--------|--------|
| **#77** | `.claude/skills/skill-config.yml` | CREATE | New shared constants file (repo, project IDs, JIRA prefix, paths) |
| **#77** | `.claude/skills/{backlog-groom,branch-cleanup,create-issue,create-pr,defer-pr-comments,guide-friction-sync,handoff,migrate,plan-parallel-streams,review-pr,sprint-close,sprint-kickoff,wave-execute}/SKILL.md` | MODIFY | Replace hardcoded constants with `$CONFIG.*` references (13 files) |
| **#78** | `.claude/skills/sprint-close/SKILL.md` | MODIFY | Replace `projectV2(number: 26)` → `23` at lines 151, 160; update Status field ID |
| **#79** | `.claude/skills/wave-execute/SKILL.md` | MODIFY | Add explicit Edit-tool step to Phase 3 (status table → in-progress) |
| **#80** | `.claude/skills/wave-execute/SKILL.md` | MODIFY | Phase 0.6 stash logic: `--include-untracked`, count any non-empty line |
| **#81** | `.claude/skills/wave-execute/SKILL.md` | MODIFY | Phase 5 final summary template: single `/sprint-close --batch` command |
| **#82** | `.claude/skills/wave-execute/SKILL.md` | MODIFY | Phase 0: new substep — `git worktree list` filtered by `--merged origin/master` |
| **#83** | `.claude/skills/sprint-close/SKILL.md` | MODIFY | Phase 6.5: secondary trigger via `gh pr view --json files` |
| **#84** | `.claude/skills/plan-parallel-streams/SKILL.md` | MODIFY | Step 5.1 status table template: add `Wave` column |
| **#84** | `.claude/skills/sprint-close/SKILL.md` | MODIFY | Phase 6 wave-completion check: filter by `Wave` column |

### Code issues — verified footprints

| Issue | Path | Change | Reason |
|-------|------|--------|--------|
| **#89** | `app.py` | MODIFY | Add `redis` key to `/readyz` `checks` map; 1s socket timeout; omit if no `REDIS_URL` |
| **#89** | `tests/test_health.py` (or `tests/test_app.py`) | MODIFY | Three new test cases: healthy Redis, unreachable Redis, no REDIS_URL |
| **#90** | `Dockerfile` | MODIFY | **Worker CMD only**: add `--concurrency`, `--prefetch-multiplier`, `--without-gossip --without-mingle --without-heartbeat` (or env-driven). **Beat CMD**: leave existing flags untouched — these options are worker-only and `celery beat` will fail to start if applied. Beat-specific tuning (e.g., `--max-interval`, scheduler choice) is a separate concern, out of scope here. |
| **#90** | `docker-compose.yml` | MODIFY | Pass `CELERY_WORKER_CONCURRENCY`, `CELERY_QUEUES` env to worker service |
| **#90** | `config.py` | MODIFY | New dataclass fields: `CELERY_WORKER_CONCURRENCY`, `CELERY_QUEUES`, `worker_prefetch_multiplier`, `result_expires` |
| **#90** | `celery_app.py` | MODIFY | Apply `task_acks_late=True`, `worker_prefetch_multiplier=1`, `result_expires` from config |
| **#99** | `tasks/print_request_tasks.py` | MODIFY | Remove `upload_jira_attachment` (and unused `JiraAttachmentUploadError` import) **or** wire it via `.delay()` from `create_jira_ticket` |
| **#99** | `tests/test_print_request_tasks.py` | MODIFY | Update or remove `upload_jira_attachment` tests accordingly |
| **#100** | `tools/system_locator/system_locator_app.py` | MODIFY | Add `_validate_jira_connectivity()` helper; call before `_sync_jira_import_task.delay()` at the confirm action |
| **#100** | `tests/test_system_locator.py` | MODIFY | Tests: pre-flight-fail → form-error; pre-flight-pass → task-dispatched |
| **#103** | `docs/guide-friction.md` | MODIFY | Append portal a11y audit findings + FW design system reference (already started via comment on issue #103) |
| **#103** | External: `qe-architecture-ai-assisted-guide/docs/patterns/frontend/design-system-for-flask-templates.md` | CREATE | Out-of-repo pattern write-up; can be a separate PR against the guide repo |
| **#103** | `docs/CLEANUP_PLAN.md` (optional) | MODIFY | Add Slice H design-system entry referencing the new guide pattern |

### Migration conflict pre-check (Step 1.3)

**No migrations required in Sprint 6.** All changes are skill docs, Flask app modifications, Celery tuning, dead-code cleanup, and documentation. Alembic adoption is in Slice D-part2 (Sprint 7).

---

## File Overlap Matrix (Phase 2)

### Wave 1 streams only

|  | A (wave-exec) | B (sprint-close + ppls) | D (#89) | E (#90) | F (#99) | G (#100) | H (#103) |
|--|--|--|--|--|--|--|--|
| **A** (#79,80,81,82) | — | 0% | 0% | 0% | 0% | 0% | 0% |
| **B** (#78,83,84) |  | — | 0% | 0% | 0% | 0% | 0% |
| **D** (#89) |  |  | — | 0% | 0% | 0% | 0% |
| **E** (#90) |  |  |  | — | 0% | 0% | 0% |
| **F** (#99) |  |  |  |  | — | 0% | 0% |
| **G** (#100) |  |  |  |  |  | — | 0% |
| **H** (#103) |  |  |  |  |  |  | — |

**Zero overlap between any Wave 1 stream pair.** Each stream targets a distinct surface — different SKILL.md files, different Python modules, different docs files.

### Wave 1 → Wave 2 overlap (informational)

| Wave 2 stream | Overlaps Wave 1 streams | Risk |
|---|---|---|
| **C** (#77 skill-config.yml) | A (wave-execute SKILL.md), B (sprint-close + plan-parallel-streams SKILL.md) | HIGH on every SKILL.md — by design |

**Why C must wait for Wave 1:** #77 touches every SKILL.md to replace hardcoded constants with `$CONFIG.*` references. If C ran in parallel with A or B, it would HIGH-overlap conflict on the same lines those streams are editing. Serializing #77 after Wave 1 lets each Wave 1 stream make its targeted fix first, then C does a clean cross-cutting refactor over the merged result.

### Shared files

None within Wave 1. Wave 2 (#77) has expected HIGH overlap with Wave 1 SKILL.md files — this is the natural design.

---

## Stream Definitions (Phase 3)

### Stream A: wave-execute SKILL.md fixes
- **Issues**: #79, #80, #81, #82 (4 bugs/enhancements in `wave-execute/SKILL.md`)
- **Why grouped**: 100% file overlap — all four touch the same SKILL.md
- **SP estimate**: 4 (Total: 1+0.5+0.5+1+1 with shared file overhead)
- **Worktree**: `../lab-tech-portal-sprint-6-A-wave-execute-fixes`
- **Branch**: `feature/sprint-6-A-wave-execute-fixes`
- **Files**: `.claude/skills/wave-execute/SKILL.md`
- **Test plan**: Markdown only; verify via grep that each AC symbol is present (e.g., `--include-untracked`, `--batch`, `git worktree list.*merged`)
- **Internal ordering**: #80 (Phase 0.6) → #82 (Phase 0 stale-worktree) → #79 (Phase 3 in-progress) → #81 (Phase 5 batch)

### Stream B: sprint-close + plan-parallel-streams SKILL.md fixes
- **Issues**: #78, #83, #84 (sprint-close has #78 + #83 + Phase 6 from #84; plan-parallel-streams has Step 5.1 from #84)
- **Why grouped**: #84 spans both files; bundling with #78 and #83 (both sprint-close) avoids two-PR rebase dance
- **SP estimate**: 3
- **Worktree**: `../lab-tech-portal-sprint-6-B-sprint-close-fixes`
- **Branch**: `feature/sprint-6-B-sprint-close-fixes`
- **Files**: `.claude/skills/sprint-close/SKILL.md`, `.claude/skills/plan-parallel-streams/SKILL.md`
- **Test plan**: Grep verification of `projectV2(number: 23)`, `gh pr view --json files`, `| Wave |` in status-table template
- **Internal ordering**: #78 (project number fix) → #84 (Wave column in both files) → #83 (friction trigger)

### Stream D: Redis health check in /readyz
- **Issues**: #89 (slice-c-resilience, observability)
- **SP estimate**: 1
- **Worktree**: `../lab-tech-portal-sprint-6-D-redis-readyz`
- **Branch**: `feature/sprint-6-D-redis-readyz`
- **Files**: `app.py`, `tests/test_health.py` (or wherever `/readyz` tests live)
- **Test plan**: Three new test cases per the issue ACs

### Stream E: Celery worker production tuning
- **Issues**: #90 (slice-c-resilience)
- **SP estimate**: 3
- **Worktree**: `../lab-tech-portal-sprint-6-E-celery-tuning`
- **Branch**: `feature/sprint-6-E-celery-tuning`
- **Files**: `Dockerfile`, `docker-compose.yml`, `config.py`, `celery_app.py`
- **Test plan**: Unit test for config field defaults; smoke test that `docker compose up worker` starts cleanly with tuning flags
- **5-tool coverage**: Stream E's PR description **must** include the required 5-row coverage matrix per [AGENTS.md:67-75](../../AGENTS.md#L67-L75). Expected outcome: all 5 rows marked `Applied` — Celery worker tuning is shared infra that benefits every tool when it dispatches async tasks (Print Requests already does, others will follow). Do not mark as N/A.

### Stream F: print-requests dead-code cleanup
- **Issues**: #99 (slice-c-resilience, Wave 3 follow-up)
- **SP estimate**: 2
- **Worktree**: `../lab-tech-portal-sprint-6-F-dead-code-cleanup`
- **Branch**: `feature/sprint-6-F-dead-code-cleanup`
- **Files**: `tasks/print_request_tasks.py`, `tests/test_print_request_tasks.py`
- **Decision required at kickoff**: Remove (simpler, recommended) vs Wire (more work, requires chaining design). Default to **Remove** unless an in-line comment in `create_jira_ticket` reveals the attachment was meant to be deferred.

### Stream G: system-locator Jira pre-flight validation
- **Issues**: #100 (slice-c-resilience, Wave 3 follow-up)
- **SP estimate**: 2
- **Worktree**: `../lab-tech-portal-sprint-6-G-jira-preflight`
- **Branch**: `feature/sprint-6-G-jira-preflight`
- **Files**: `tools/system_locator/system_locator_app.py`, `tests/test_system_locator.py`
- **Implementation note**: `JiraService` does not currently have a lightweight pre-flight helper. Stream G must add one — e.g., a `validate_connectivity()` method that calls Jira's `/rest/api/2/myself` endpoint (cheap authenticated read), or reuse `search_issues` with a trivial JQL like `project = NONEXISTENT-1234`. Existing methods (`get_issue`, `create_lab_request`, etc.) are too heavy or have side effects.

### Stream H: UI design system foundations + portal a11y audit
- **Issues**: #103 (slice-h-closure, Wave 3 carry-forward)
- **SP estimate**: 3 (within-repo portion; the architecture-guide pattern write-up is a separate PR in `qe-architecture-ai-assisted-guide`)
- **Worktree**: `../lab-tech-portal-sprint-6-H-design-system-audit`
- **Branch**: `feature/sprint-6-H-design-system-audit`
- **Files**: `docs/guide-friction.md`, optionally `docs/CLEANUP_PLAN.md`, optionally `static/style.css` (if audit findings include immediate token extraction)
- **Reference**: The FW Testing Platform design system foundations (colors, spacing, typography, dark mode, WCAG 2.1 AA checklist) are the source of truth for Stream H. These docs live in a separate repository on the maintainer's workstation and are **not committed to this repo**. Operator must either (a) pre-snapshot the relevant foundations files into `docs/references/design-system-fw/` before launching the Stream H agent, OR (b) provide snippets to the agent at kickoff time. The agent should not be pointed at any absolute filesystem path. See [issue #103 comment](https://github.com/adc-quality/lab-tech-portal/issues/103#issuecomment-4452560491) for the breakdown of which foundations transfer to the portal's Flask/Jinja2 stack.
- **Scope cap**: This stream produces the audit + recommendations; the architecture-guide pattern write-up is a follow-on PR in a separate repo and does NOT count toward Sprint 6's portal scope

### Stream C: Skill-config.yml cross-cutting (Wave 2)
- **Issues**: #77
- **SP estimate**: 3
- **Worktree**: `../lab-tech-portal-sprint-6-C-skill-config`
- **Branch**: `feature/sprint-6-C-skill-config`
- **Files**: `.claude/skills/skill-config.yml` (CREATE) + all 13 `.claude/skills/*/SKILL.md` files (MODIFY)
- **Why Wave 2**: HIGH overlap with Wave 1 Streams A and B on wave-execute, sprint-close, plan-parallel-streams SKILL.md files. Wait for those to land, then refactor over the merged result.
- **Pre-flight**: At kickoff time, rebase against current master and re-verify file list — Wave 1 may have added new files or sections that should also be parameterized

### Dependency graph

```
Stream A ──┐
Stream B ──┤
Stream D ──┤
Stream E ──┼──► Wave 1 (all parallel, zero overlap)
Stream F ──┤
Stream G ──┤
Stream H ──┘
            │
            ▼ (Wave 1 must merge before Wave 2)
Stream C  ───► Wave 2 (cross-cutting consolidation)
```

---

## Agent Team Allocation (Phase 4)

| Stream | Issues | SP | Classification | Dev model | QE model |
|--------|--------|----|----|------------|----------|
| A | #79, #80, #81, #82 | 4 | Standard (multi-issue, single file) | Sonnet | Haiku |
| B | #78, #83, #84 | 3 | Standard | Sonnet | Haiku |
| D | #89 | 1 | Trivial | Haiku | Haiku |
| E | #90 | 3 | Standard (multi-file, infra) | Sonnet | Haiku |
| F | #99 | 2 | Trivial (cleanup) | Haiku | Haiku |
| G | #100 | 2 | Standard | Sonnet | Haiku |
| H | #103 | 3 | Standard (docs + audit) | Sonnet | Haiku |
| C | #77 | 3 | Complex (cross-cutting, 14 files) | Sonnet | Sonnet |

**Shared agents:**
- **Architect** (Opus): one-shot overlap recheck at Wave 1 kickoff against current master
- **Critic** (Haiku): pre-PR gate for each stream

### Capacity plan

| Wave | Streams | Parallel agents | Est. duration | Bottleneck |
|------|---------|-----------------|---------------|------------|
| 1 | 7 | 7 Dev + 7 QE | ~2–3h | Stream E (#90, multi-file Celery + Docker) or H (#103, audit pass) |
| 2 | 1 | 1 Dev + 1 QE | ~1h | Stream C (#77, cross-cutting refactor with rebase concerns) |

---

## Conflict-cutting rules

1. **Rebase daily**: `git fetch origin && git rebase origin/master` on every active worktree
2. **Migration numbering check before branching**: N/A this sprint — no migrations
3. **Overlap check before promoting any new branch to parallel**:
   ```bash
   comm -12 <(gh pr diff NNN --name-only | sort) <(git diff master --name-only | sort)
   ```
   If overlap > 30%, wait for the first PR to merge or merge the branches.
4. **Push review fixes to the PR being reviewed** — never sidecar them onto another active branch
5. **PR titles require `QENG-16846:` prefix** and conventional commit scope
6. **One concern per PR** — line budget 600. Streams A and C are at risk:
   - **Stream A**: 4 issues in one SKILL.md — may exceed 600 if each fix is verbose. If approaching limit, split into two PRs (e.g., bugs #79 + #80 first, enhancements #81 + #82 second).
   - **Stream C**: 14 files touched. Pre-split: PR 1 = create `skill-config.yml` + add Step 0 preamble to all SKILL.md files; PR 2 = replace hardcoded constants with `$CONFIG.*` references.
7. **Worktree cleanup**: `git worktree remove <path>` immediately after PR merge
8. **No `innerHTML` for server-sourced data** (new AGENTS.md hard rule from Sprint 5 Wave 3 — relevant if Stream H's audit fixes any polling JS)

---

## Status tracking table

| Wave | Stream | State | Branch | PR | Depends on | Blockers |
|------|--------|-------|--------|----|------------|----------|
| 1 | A | **merged** | `feature/sprint-6-A-wave-execute-fixes` | #108 | — | none |
| 1 | B | **merged** | `feature/sprint-6-B-sprint-close-fixes` | #112 | — | none |
| 1 | D | **merged** | `feature/sprint-6-D-redis-readyz` | #110 | — | none |
| 1 | E | **merged** | `feature/sprint-6-E-celery-tuning` | #111 | — | none |
| 1 | F | **merged** | `feature/sprint-6-F-dead-code-cleanup` | #109 | — | none |
| 1 | G | **merged** | `feature/sprint-6-G-jira-preflight` | #113 | — | none |
| 1 | H | **merged** | `feature/sprint-6-H-design-system-audit` | #114 | — | none |
| 2 | C | **merged** | `feature/sprint-6-C-skill-config` | #117 | — | none (Wave 1 merged 2026-05-14) |

(Note: this status table format is the same one #84 is supposed to add the `Wave` column to — that column is included here as a forward-fit since Stream B will land #84 during Sprint 6.)

---

## Pre-flight checklist (do once before spawning agents)

- [ ] **Close #105 with comment**: `ACs already satisfied — Step 0.3.5 added to wave-execute/SKILL.md in Sprint 5 Wave 3 (commit f538ee3 / PR #106 squash). Verified by Phase 0 pre-flight check.`
- [ ] `git checkout master && git pull --ff-only` — confirm clean tree at `996b4d6` or newer
- [ ] `git tag -d pre-sync-recovery-2026-05-14` — delete the Sprint 5 wrap-up safety tag (no longer needed)
- [ ] `git branch -d docs/sprint-5-wave-3-close` — local branch from PR #106, merged
- [ ] Verify no in-flight migrations on remote: `git ls-remote origin | grep migrations` (expect empty)
- [ ] At Wave 1 kickoff: Architect agent runs overlap check against current master for all 7 Wave 1 streams
- [ ] Each Dev agent gets: stream row from table + issue bodies + this plan as context
- [ ] Confirm Docker services healthy (when Stream E starts): `docker compose ps`

---

## Action items beyond Sprint 6 execution

1. **Close #105** (shipped) — see pre-flight checklist
2. **File issue against `qe-repo-ai-assisted-guide`** for the `adc_github_sdk` import failure that has blocked #45 (qe-check baseline) since Sprint 3. Title suggestion: `bug(qe-check): adc_github_sdk module missing — blocks baseline run in adopter projects`
3. **Backlog grooming during Sprint 6** to create Slice G-part1 Docker foundations tickets (~6 issues per Wave 3 estimate). Source the scope from `docs/CLEANUP_PLAN.md` line 129–141. These become Sprint 7 Wave 1 candidates.
4. **Triage #91 and #98** during Sprint 6 — neither was scoped here per Wave 3 guidance. #91 (inventory QR for API path) is a P3 nice-to-have; #98 (OpenAPI Swagger 2.0 → OAS 3.0) is a Slice H closure item. Decide: Sprint 7 scope or defer.

---

## Notes for `/wave-execute` consumption

- The Phase 0.3.5 under-load check (added in Sprint 5 Wave 3 as part of #105) will fire on Wave 2 because it has only 1 stream. **This is expected and not a problem** — Wave 2 is the natural serialization of #77's cross-cutting refactor. Confirm/dismiss the under-load prompt at Wave 2 kickoff and proceed.
- Stream C (#77) is **the issue's own self-test**: it must successfully consume the `skill-config.yml` it creates. After merging, run any other skill (e.g., `/sprint-close`) and verify the `$CONFIG.*` references resolve correctly. If the consumption mechanism is "read this file before each invocation" rather than templated substitution, document that pattern in the resulting PR.
