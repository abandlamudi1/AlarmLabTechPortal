# Sprint 2 — Parallel Execution Plan

**Date:** 2026-05-12
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams`)
**Milestone / focus:** Sprint 2 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor slice:** Slice A — Identity, Access & Web Security
**Goal:** Land Slice A and ship two non-overlapping parallel streams (Docker infra and docs/baseline) in the same wave, then plan Sprint 3 from a clean Slice A foundation.

---

## Pre-flight state

| Item | State | Notes |
|---|---|---|
| `master` | clean | PR #42 (Slice 0a scaffolding) merged |
| PR #43 (Slice 0b deferred init) | **merged** | `app.py` is unblocked — no longer a Slice A precondition |
| `services/okta_auth.py` | exists | Slice A extends `groups` claim handling |
| `config.py` | exists with full validation logic | See Pre-flight AC verification below |
| `.env.example` | exists with Slice A env vars defined | Same — wiring is the remaining work |

---

## Pre-flight AC verification (Phase 0 of plan-parallel-streams)

A footprint sub-agent checked Slice A's stated ACs against the current `master`. Two issues turned out to be **Partial** — the underlying primitives shipped in Slice 0, but app code doesn't consume them yet.

| Issue | Stated AC | Verified state | Revised scope |
|-------|-----------|----------------|---------------|
| #6 — Extract hardcoded values | Move PIN/defaults to env vars | `config.py:97-117` already defines `SYSTEM_LOCATOR_DELETE_PIN`, `PRINT_REQUESTS_DEFAULT_*`. Tool code still references hardcoded values at `tools/system_locator/system_locator_app.py:417` and `tools/print_requests/print_requests_app.py:334-336`. | **Partial** — consume the existing env vars in tool code; do not re-define them in `config.py` |
| #11 — Startup config validation | Wire fail-fast validation | `config.py:181-218` (validate_config) and `config.py:235-249` (init_app) already exist. `app.py:27` still uses bare `os.environ.get("SECRET_KEY")`. | **Partial** — call `config.init_app(app)` from `app.py`; no new validator logic |
| #36 — CSRF + rate limit + headers | All as stated | No primitives exist yet | **Open** — proceed as written |
| #44 — RBAC tiers (warn-only) | All as stated | `services/rbac.py` does not exist; `services/okta_auth.py` exists but doesn't extract `groups` claim | **Open** — proceed as written |

**Action:** When the Stream A Dev agent is briefed, the prompt for #6 and #11 must call out the "wire only, do not re-define" framing so the agent doesn't reinvent existing config.py logic.

---

## File-overlap matrix

Three candidate streams analyzed. Footprint discovered per stream by Explore sub-agents.

|              | Stream A (auth) | Stream B (docker) | Stream C (docs+baseline) |
|--------------|----------------|-------------------|--------------------------|
| **A (auth)** | —              | **soft edge**     | 0%                       |
| **B (docker)** |               | —                 | **soft edge**           |
| **C (docs+baseline)** |        |                   | —                       |

### Shared files

| File | Streams | Risk | Mitigation |
|------|---------|------|------------|
| `requirements.txt` | A, B | LOW (soft edge) | A adds `Flask-WTF`, `Flask-Limiter`. B segregates dev deps and adds Gunicorn to a NEW `requirements-prod.txt`. If B also edits `requirements.txt`, conflicts are additive — accept both. |
| `README.md` | B (Docker quickstart), C (#38 architecture update may touch README) | LOW (soft edge) | **All README edits route through Stream C.** Stream B drafts its Docker quickstart blurb in the PR description; Stream C lifts it into README. |

**Zero overlap** on every other file across the three streams. No HIGH-risk shared files in Wave 1.

---

## Stream definitions

### Stream A — Slice A: Identity / Auth / Web Security
- **Issues:** #6, #11, #36, #44 (work in this order — #6 → #11 → #36 → #44 each enable the next)
- **Branch:** `feature/sprint-2-slice-a-auth`
- **Worktree:** `../lab-tech-portal-sprint-2-slice-a`
- **Size:** L (multi-tool CSRF rollout dominates)
- **File footprint:**
  - `app.py` (heavy: wire config.init_app, CSRFProtect, Flask-Limiter, RBAC middleware, Okta groups extraction)
  - `config.py` (light: add CSRF_ENABLED, RATELIMIT_*, CORS_ORIGINS, SECURE_COOKIE_* fields if not yet present)
  - `requirements.txt` (add Flask-WTF≥1.2.0, Flask-Limiter≥3.5.0)
  - `.env.example` (CSRF/ratelimit/CORS sections)
  - `services/okta_auth.py` (extract `groups` claim)
  - `services/rbac.py` (NEW — `@requires_role` decorator + warn-only mode)
  - `tools/system_locator/system_locator_app.py` (consume `SYSTEM_LOCATOR_DELETE_PIN`; annotate `/hard-delete`)
  - `tools/print_requests/print_requests_app.py` (consume `PRINT_REQUESTS_DEFAULT_*`)
  - **All 5 tools' templates** (inject `{{ csrf_token() }}` into POST forms — Inventory, RF Chamber, Checkout, System Locator, Print Requests)
  - `tests/conftest.py` (config fixture)
  - `tests/test_pin_protected_delete.py` (read PIN from injected config)
  - `tests/test_config_validation.py` (NEW)
  - `tests/test_csrf_protection.py` (NEW)
  - `tests/test_ratelimit.py` (NEW)
  - `tests/test_rbac.py` (NEW)
- **Pattern citation:** `docs/patterns/auth/multi-mode-auth.md` (qe-architecture-ai-assisted-guide @ <SHA at branch creation>)
- **Hard rule:** the legacy hard-delete PIN literal MUST NOT appear in source after this stream. The PIN moves to `SYSTEM_LOCATOR_DELETE_PIN`; verification step is `grep -rE "\"[0-9]{4}\"" tools/system_locator/ services/ | grep -v test_` returns 0 hits matching the legacy literal. See [config.py](../../config.py) for the env-var binding.
- **RBAC mode:** ships **warn-only** (log denials, return 200). Enforcement flips in Sprint 3.

### Stream B — Slice G-part1: Docker / WSGI / CI
- **Issues:** #5, #19, #20, #22, #23, #25 (work in dependency order: #5+#22 (wsgi/entrypoint) → #19 (Dockerfile) → #20 (compose) → #23 (compose.dev override) → #25 (CI workflow))
- **Branch:** `feature/sprint-2-slice-g-part1-docker`
- **Worktree:** `../lab-tech-portal-sprint-2-slice-g-part1`
- **Size:** M-L (all new files; ~8 new artifacts)
- **File footprint:**
  - `wsgi.py` (NEW)
  - `entrypoint.sh` (NEW)
  - `requirements-prod.txt` (NEW — Gunicorn + prod-only deps)
  - `requirements.txt` (light segregation; see soft edge mitigation)
  - `Dockerfile` (NEW — multi-stage: base, web, worker, beat targets)
  - `docker-compose.yml` (NEW — web, worker, beat, redis services; volumes)
  - `docker-compose.dev.yml` (NEW — hot-reload override)
  - `.github/workflows/ci.yml` (NEW — `.github/workflows/jira-check.yml` already exists and is untouched)
- **Note on Celery:** Dockerfile/compose define `worker` and `beat` targets, but they are non-functional until Slice C (Sprint 3). Stream B ships the topology; Slice C activates it.
- **5-tool coverage matrix:** every change is repo-wide, so the coverage matrix is "Applied to all 5" with one row noting which tool drove which env-var seam (e.g., `DATA_DIR` volume mount lands for all 5 tools simultaneously).

### Stream C — Docs + Baseline
- **Issues:** #38 (architecture.md + Docker runbook), #50 (Kubernetes ops runbook), #45 (qe-check baseline → guide-friction.md)
- **Branch:** `feature/sprint-2-docs-baseline`
- **Worktree:** `../lab-tech-portal-sprint-2-docs-baseline`
- **Size:** S
- **File footprint:**
  - `architecture.md` (MODIFY — Docker topology, Celery workers, Redis)
  - `docs/DOCKER_RUNBOOK.md` (NEW)
  - `docs/runbook-k8s.md` (NEW)
  - `docs/API_REFERENCE.md` (NEW — initial scaffold; full API docs come with Slice C's `/api/v1/`)
  - `README.md` (MODIFY — Docker quickstart, supplied by Stream B's PR description)
  - `docs/guide-friction.md` (APPEND — qe-check baseline output as `F04` entry)
- **Note:** #50 (k8s runbook) is partially speculative — k8s manifests don't exist until Slice G-part2 (Sprint 5+). Land it as a skeleton runbook that will be filled in then; flag clearly in the doc.
- **Pre-condition for the agent:** **must wait for Stream B's docker-compose.yml to be drafted** before finalizing the Docker runbook content. Sequence inside the stream: #45 baseline → start #38 (architecture diagram) → wait for Stream B PR → finish #38 (runbook commands) → ship #50 skeleton.

---

## Dependency graph

```
PR #43 (merged) ────► All Wave 1 streams unblocked
                       │
                       ├──► Stream A (Slice A auth) ────────┐
                       │                                     │
                       ├──► Stream B (Docker infra) ─┐       │
                       │                              │       │
                       └──► Stream C (docs+baseline)  │       │
                              └─ depends on Stream B  │       │
                                 for runbook content  ▼       ▼
                                                  Wave 1 merges
                                                       │
                                                       ▼
                                            Sprint 3 (Slice B observability)
                                            — needs Slice A merged because
                                              /healthz + logging middleware
                                              register on app.py
```

**Wave 1** (this sprint): Stream A, Stream B, Stream C — run **in parallel**, merge in any order.
**Wave 2** (Sprint 3): Slice B observability, Slice D-part1 (DATA_DIR centralization). Both depend on Wave 1.

---

## Agent team allocation

| Stream | Dev agent model | QE agent model | Rationale |
|--------|-----------------|----------------|-----------|
| A — Slice A auth | **Sonnet** | **Sonnet** | Complex: multi-system (auth + CSRF + RBAC + 5-tool template rollout). Tests must cover warn-only behavior. |
| B — Docker infra | **Sonnet** | **Haiku** | Standard: well-defined Dockerfile + compose patterns; QE just verifies images build and stack starts. |
| C — Docs + baseline | **Haiku** | n/a (self-review) | Trivial: docs only. Baseline #45 is a recorded shell-command output. |

**Shared roles:**
- **Architect (Opus, one-shot at kickoff):** re-check overlap matrix against current `master` immediately before spawning the Dev agents. Should take <10 min.
- **Critic (Haiku, pre-PR gate per stream):** runs the DoD checklist before each agent opens its PR.

---

## Line-budget enforcement

Every Dev agent prompt includes:
> **Line budget:** Your PR diff must NOT exceed 600 lines (additions + deletions). If your changes approach this limit, STOP, split into logical sub-PRs on the same branch, ensure each is independently CI-green, and continue.

**Pre-split prediction:**
- Stream A is at risk of >600 lines (5-tool CSRF template rollout alone may be ~200 lines; new tests another ~250). If observed at ~500, split as:
  - **PR 1**: #6 + #11 + #36 backend (CSRF/limiter + env-var consumption) + tests
  - **PR 2**: #36 template rollout across 5 tools + #44 RBAC + tests
- Stream B fits in 600 (≈400 across Dockerfile/compose/wsgi/entrypoint + CI ~120).
- Stream C fits in 600 easily.

---

## Conflict-cutting rules (inherited from project conventions)

1. **Rebase daily:** `git fetch origin && git rebase origin/master` on every active worktree.
2. **One concern per PR.** If a stream grows past ~600 lines, split.
3. **PR titles** require `QENG-16846:` prefix and conventional commit form: `QENG-16846: <type>(<scope>): <summary>`.
4. **5-tool coverage matrix** populated in every infrastructure PR description (Stream A, Stream B).
5. **Pattern citation** in new code: `# Pattern: docs/patterns/<...>.md (qe-architecture-ai-assisted-guide @ <SHA>)`.
6. **Guide-friction**: any pattern ambiguity → entry in [docs/guide-friction.md](../guide-friction.md). Bundle for Slice H close-out via `/guide-friction-sync` (see companion sketch).
7. **Worktree cleanup**: `git worktree remove <path>` immediately after PR merge — `/sprint-close` handles this.
8. **README ownership**: Stream B does NOT edit `README.md` directly. It drafts Docker-quickstart copy in the PR description; Stream C lifts it.

---

## Status tracking

| Stream | State | Branch | PR | Depends on | Blockers |
|--------|-------|--------|----|-|----------|
| A — Slice A auth | **merged** (2026-05-13) | `feature/sprint-2-slice-a-auth` | #60 | — | none |
| B — Docker infra | **merged** (2026-05-13) | `feature/sprint-2-slice-g-part1-docker` | #58 | — | none |
| C — Docs + baseline | **merged** (2026-05-13) | `feature/sprint-2-docs-baseline` | #59 | — | Issue #45 left open (qe-check install blocker — F04) |

**Wave 1 complete.** All 3 PRs merged. 12 of 13 issues closed (#45 intentionally deferred to Sprint 3 once qe-check install is unblocked).

Update this table as PRs open and merge. `/sprint-close` updates rows on each merge.

---

## Pre-flight checklist (run once before spawning Wave 1 agents)

- [ ] `git checkout master && git pull` — clean tree
- [ ] Confirm PR #43 is merged on `master`: `git log --oneline master | head -5` shows `7de67ec`
- [ ] Architect agent (Opus, one-shot) re-runs overlap check against current `master`
- [ ] Three worktrees exist:
  - `git worktree add ../lab-tech-portal-sprint-2-slice-a feature/sprint-2-slice-a-auth`
  - `git worktree add ../lab-tech-portal-sprint-2-slice-g-part1 feature/sprint-2-slice-g-part1-docker`
  - `git worktree add ../lab-tech-portal-sprint-2-docs-baseline feature/sprint-2-docs-baseline`
- [ ] Each Dev agent gets: its stream row from this table + linked issue bodies + this plan as context + the pre-flight scope correction for #6 / #11
- [ ] Stream A agent briefed: legacy hard-delete PIN scrub rule (env-var only, no literal in source), RBAC warn-only mode, 5-tool template coverage matrix
- [ ] Stream C agent briefed: wait for Stream B compose draft before completing #38 runbook
- [ ] `.env.example` reviewed for completeness — Stream A only adds CSRF/ratelimit/CORS fields, does not re-add Slice A vars

---

## DoD per stream

Stream A — opens PR when:
- [ ] `python -m pytest` passes (existing tests green + new tests for config validation / CSRF / ratelimit / RBAC)
- [ ] The legacy hard-delete PIN literal is not present anywhere outside test fixtures — verified by grepping for any 4-digit string-literal in `tools/system_locator/` and `services/` and confirming no match for the pre-extraction value (only `SYSTEM_LOCATOR_DELETE_PIN` references should remain)
- [ ] `python app.py` starts cleanly with valid env
- [ ] `SECRET_KEY="change-me" FLASK_ENV=production python app.py` raises `ValueError` from startup validation
- [ ] RBAC warn-only: admin route request from non-admin logs WARNING but returns 200
- [ ] PR description has 5-tool coverage matrix populated
- [ ] Issues #6, #11, #36, #44 close on PR merge with PR reference

Stream B — opens PR when:
- [ ] `docker build -f Dockerfile --target web .` succeeds
- [ ] `docker compose up` starts web + redis + (worker stub + beat stub)
- [ ] `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` mounts source for hot-reload
- [ ] `.github/workflows/ci.yml` parses (`gh workflow view ci.yml --repo adc-quality/lab-tech-portal` after push)
- [ ] PR description has 5-tool coverage matrix
- [ ] Docker-quickstart blurb included for Stream C to lift into README
- [ ] Issues #5, #19, #20, #22, #23, #25 close on PR merge

Stream C — opens PR when:
- [ ] `architecture.md` updated with Docker/Celery/Redis topology
- [ ] `docs/DOCKER_RUNBOOK.md` covers: start/stop, logs, backup/restore, env vars, common debugging
- [ ] `docs/runbook-k8s.md` skeleton with placeholders flagged for Slice G-part2 fill-in
- [ ] `docs/API_REFERENCE.md` scaffolded
- [ ] `docs/guide-friction.md` appended with `F04 — qe-check baseline (Slice 0)` entry containing raw checker output
- [ ] `README.md` quickstart section from Stream B's PR description integrated
- [ ] Issues #38, #50, #45 close on PR merge

---

## Capacity plan

| Wave | Streams | Parallel agents | Est. wall-clock | Bottleneck |
|------|---------|-----------------|-----------------|------------|
| 1    | 3       | 3 Dev + 2 QE    | ~2 sessions     | Stream A (5-tool rollout) |
| —    | —       | —               | —               | Stream C blocks until Stream B's compose drafted |

**Total Sprint 2 footprint:** 13 issues closed across 3 PRs (Slice A: 4, Slice G-part1: 6, Docs+baseline: 3).

---

## Next step

Invoke `/sprint-kickoff --plan docs/sprint-plans/sprint-2-execution-plan-2026-05-12.md --wave 1` (or the local equivalent) to:
1. Create the three worktrees
2. Generate per-agent prompts from each stream row
3. Launch the Dev (+ QE) agents in parallel

After Wave 1 merges, `/sprint-close` per PR clears worktrees and updates the status table above. Sprint 3 planning then re-runs `/plan-parallel-streams` against the remaining backlog with Slice B observability + Slice D-part1 as anchor candidates.
