# Sprint 3 — Parallel Execution Plan

**Date:** 2026-05-13
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams`)
**Milestone / focus:** Sprint 3 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor slice:** Slice B — Observability foundation (`/healthz`, structured logging) + Slice D-part1 (DATA_DIR + DB hygiene)
**Goal:** Land the observability primitives Sprint 4+ depends on, AND finish the data-layer foundations PR #58's volumes already presume.

---

## Pre-flight state

| Item | State | Notes |
|---|---|---|
| `master` tip | `81d85b9` | Wave 1 merged: PR #58 (Docker), PR #59 (docs), PR #60 (Slice A auth) |
| 12 issues closed via Wave 1 | done | #5, #11, #19, #20, #22, #23, #25, #36, #44, #6 (auto), #38 (auto), #50 |
| Issue #45 (qe-check baseline) | open, deferred | F04 in docs/guide-friction.md — qe-check install blocked by adc-jira-sdk |
| `docker-compose.yml` DATA_DIR mounts | already wired | App code does not yet read DATA_DIR — Stream B's anchor |
| `Dockerfile` HEALTHCHECK | hits `/` with `TODO(Slice-B)` | Stream A delivers `/healthz` to retire that TODO |
| `services/rbac.py` warn-only mode | shipped | Stream A's audit-log decision (deferred to Wave 3) gates the enforce flip |

---

## Pre-flight AC verification (Phase 0)

Sub-agent footprinting on the candidate issue set against current `master`:

| Issue | Stated AC | Verified state | Revised scope |
|-------|-----------|----------------|---------------|
| #7 — /healthz + /readyz | Both endpoints + DB-connectivity probe | `app.py` has no /healthz; Dockerfile + compose both carry explicit `TODO(Slice-B)` comments | **Open** — proceed as written |
| #33 — Structured JSON logging | request-ID middleware + structlog + JSON formatter | Existing logging is stdlib only (`services/rbac.py`, `services/jira_service.py`); no request-ID anywhere | **Open** — proceed as written |
| #46 — Audit log table | Cross-tool audit + RBAC integration | No audit table; 5 tool apps lack any audit hook | **Open** but **deferred to Wave 3** (file overlap with Stream B — see §File-overlap matrix) |
| #2 — Centralize DATA_DIR | Wire app code to read DATA_DIR | `config.py:65` already defines DATA_DIR; tool `db.py` files still hardcode `BASE_DIR + "<tool>.db"` paths | **Partial** — wire only, config primitives exist |
| #3 — Fix absolute paths in print_requests | Relative paths + migration | DB rows hold absolute paths; `_handle_upload()` returns full FS path | **Open** — proceed as written |
| #9 — Inline DB schemas → db.py | All 5 tools have dedicated db.py | Checkout/Print Requests/System Locator already have db.py; **Inventory + RF Chamber inline schema in `*_app.py`** | **Partial** — only 2 of 5 tools need the extract |
| #24 — SQLite WAL mode | `PRAGMA journal_mode=WAL` on connect | No tool sets WAL today; some open ad-hoc connections inline | **Open** — proceed as written |
| #47 — Move QR generation to DATA_DIR/generated/ | All 5 tools | Only **Inventory** actually writes QR PNGs to disk; RF Chamber generates base64 inline at request time (no disk write) | **Partial** — Inventory-only file moves; RF Chamber comment-only |

**Surprises captured:** RF Chamber's QR scope is smaller than #47 implies. Inventory + RF Chamber both still inline DB schema (only 3 of 5 tools have done the `db.py` split). RF Chamber's CSV seed (`tools/rf_chamber/data/rf_chambers.csv`) is unmentioned in #47 but flagged in CLEANUP_PLAN §Slice D-part1 — folded into #2 scope.

---

## Stream definitions

### Stream A — Slice B observability foundation
- **Issues:** #7 (healthz/readyz), #33 (structured JSON logging + request correlation)
- **NOT in scope:** #46 (audit log) — deferred to Wave 3 to avoid 5-tool overlap with Stream B
- **Branch:** `feature/sprint-3-slice-b-observability`
- **Worktree:** `../lab-tech-portal-sprint-3-slice-b`
- **Size:** M (~300–450 lines)
- **Implementation order within stream:** #7 first (quick win, unblocks Docker healthcheck wiring) → #33 (request-ID middleware → JSON formatter → swap call sites in rbac.py + jira_service.py)
- **File footprint:**
  - `app.py` (add /healthz + /readyz routes; register request-ID middleware + structlog init)
  - `config.py` (add `LOG_FORMAT`, `STRUCTLOG_ENABLED`)
  - `services/logging_config.py` (NEW — structlog init + JSON formatter + request-ID context)
  - `services/rbac.py` (swap `logging.warning` → structlog calls; preserve format keys)
  - `services/jira_service.py` (swap a handful of stdlib logger calls)
  - `Dockerfile` (HEALTHCHECK → `/healthz`)
  - `docker-compose.yml` (web healthcheck → `/healthz`)
  - `tests/test_healthz.py` (NEW)
  - `tests/test_structured_logging.py` (NEW)
- **Pattern citation:** `docs/patterns/observability/audit-logging.md` partial (full citation when #46 lands in Wave 3)

### Stream B — Slice D-part1 data-layer foundations
- **Issues:** #2 (DATA_DIR), #9 (db.py extraction — Inventory + RF Chamber only), #24 (WAL), #47 (QR generation paths — Inventory only), #3 (print_requests absolute paths)
- **Branch:** `feature/sprint-3-slice-d-part1-data-layer`
- **Worktree:** `../lab-tech-portal-sprint-3-slice-d-part1`
- **Size:** L (~700–950 lines; concentrated in `tools/*` so reviewable)
- **Implementation order within stream:** #2 (wire DATA_DIR through existing db.py files) → #9 (extract Inventory + RF Chamber inline schemas into new db.py) → #24 (add WAL pragma in each db.py's `_get_connection()`) → #47 (Inventory QR save path → `DATA_DIR/generated/inventory/`) → #3 (relative paths + DB migration for legacy rows)
- **File footprint:**
  - `config.py` (light — documenting DATA_DIR usage; primitives exist)
  - `tools/checkout/db.py` (DATA_DIR + WAL)
  - `tools/system_locator/db.py` (DATA_DIR + WAL)
  - `tools/print_requests/db.py` (DATA_DIR + WAL; legacy-path migration logic)
  - `tools/inventory/db.py` (NEW — extract schema + DATA_DIR + WAL)
  - `tools/rf_chamber/db.py` (NEW — extract schema + DATA_DIR + WAL)
  - `tools/inventory/inventory_app.py` (consume new db.py; QR save path → `DATA_DIR/generated/inventory/`)
  - `tools/rf_chamber/rf_chamber_app.py` (consume new db.py; CSV seed path)
  - `tools/print_requests/print_requests_app.py` (rewrite `_handle_upload()` / `_handle_design_image_upload()` to store relative paths; `send_file` callers resolve via `DATA_DIR`)
  - `tests/conftest.py` (DATA_DIR fixture; legacy fixture paths)
  - `tests/test_data_dir_centralization.py` (NEW)
  - `tests/test_sqlite_wal.py` (NEW)
  - Migration script for print_requests legacy paths (one-shot SQL in `.scripts/migrate_print_paths.py` per AGENTS.md "no throwaway scripts → use .scripts/")

---

## File-overlap matrix

| | Stream A (observability) | Stream B (data-layer) |
|---|---|---|
| Stream A | — | **soft edge** |
| Stream B | | — |

### Shared files
| File | Streams | Risk | Mitigation |
|------|---------|------|------------|
| `config.py` | A, B | LOW (soft edge) | A adds `LOG_FORMAT`, `STRUCTLOG_ENABLED` near the existing fields; B only documents `DATA_DIR` (primitive exists). Additive — accept both on rebase. |
| `tests/conftest.py` | A, B | LOW | A may add a structlog capture fixture; B updates DATA_DIR fixture. Different fixtures, additive. |

**Zero overlap** on every other file — the tool app modules (`tools/*_app.py`) are Stream B's territory this wave; Stream A's audit-log integration (which would also touch them) is deferred to Wave 3.

### Why #46 is deferred to Wave 3

If audit-log integration (#46) ran in Stream A this wave, it would touch the same 5 tool app files Stream B refactors for DATA_DIR + db.py extraction. Rebase conflicts would be inevitable (different concerns, same lines). Cleaner sequence:
1. **Wave 2 (this plan):** Stream B stabilizes the tool app structure (db.py extraction, DATA_DIR wiring, WAL).
2. **Wave 3 (Sprint 3 second half):** Stream C lands #46 audit log + the RBAC enforcement flip on top of the now-stable tool structure.

---

## Dependency graph

```
Wave 1 (merged) ───► All Wave 2 streams unblocked
                       │
                       ├──► Stream A (Slice B observability) ─┐
                       │                                       │
                       └──► Stream B (Slice D-part1) ──────────┤
                                                               ▼
                                                       Wave 2 merges
                                                               │
                                                               ▼
                                                       Wave 3 (Sprint 3, second half)
                                                       — Audit log (#46)
                                                       — RBAC enforcement flip
                                                       — Small follow-ups:
                                                         · Compose profiles (worker/beat)
                                                         · Dockerfile test target split
                                                         · qe-check install fix PR
                                                           (upstream — different repo)
```

---

## Agent team allocation

| Stream | Dev agent model | Rationale |
|--------|-----------------|-----------|
| A — Slice B observability | **Sonnet** | New abstraction (request-ID context, structlog init) — needs judgment on logging shape. |
| B — Slice D-part1 | **Sonnet** | Cross-tool refactor with one DB migration; mechanical but reaches into every tool. |

No QE agents this wave — the test files are part of the same stream and Sonnet writes them inline. Sprint 4 candidate: spin out QE as a separate role when integration tests grow.

---

## Line-budget enforcement

Same rule as Wave 1: **aim for ONE PR per stream**. Only split if the diff genuinely becomes unreviewable (>1500 lines of mixed concerns). The 600-line tripwire from the standard skill is overridden.

**Pre-split prediction:** Stream B is likely the largest (~700-950 lines). If it exceeds 1500, split as:
- **PR 1:** #2 + #9 + #24 (DATA_DIR + db.py extraction + WAL) — the foundation
- **PR 2:** #47 + #3 (QR paths + print absolute paths) — built on PR 1

But default behavior: ship as one PR.

---

## Conflict-cutting rules (inherited)

1. **Rebase daily:** `git fetch origin && git rebase origin/master` on every active worktree.
2. **One concern per PR** (or pre-split per above).
3. **PR titles** require `QENG-16846:` prefix and conventional commit form.
4. **5-tool coverage matrix** in every infra PR (Stream B will have a full matrix; Stream A is repo-wide so single-row).
5. **Pattern citation** in new code where applicable: `# Pattern: docs/patterns/<area>/<file>.md (qe-architecture-ai-assisted-guide @ <SHA>)`.
6. **Guide-friction:** any pattern ambiguity → entry in `docs/guide-friction.md`.
7. **Worktree cleanup**: `/sprint-close <PR#>` after merge handles it.
8. **No README ownership conflicts** this wave (no README edits planned).

---

## Status tracking

| Stream | State | Branch | PR | Depends on | Blockers |
|--------|-------|--------|----|-|----------|
| A — Slice B observability | **merged** | `feature/sprint-3-slice-b-observability` | #61 | — | none |
| B — Slice D-part1 data layer | **merged** | `feature/sprint-3-slice-d-part1-data-layer` | #62 | — | none |

Wave 2 closed 2026-05-13. Issues closed: #7 (auto), #33, #2 (auto), #3, #9, #24, #47.

---

## Pre-flight checklist (run once before spawning Wave 2 agents)

- [x] `git checkout master && git pull` — clean tree on master at `81d85b9`
- [x] Confirm Wave 1 PRs (#58/#59/#60) all merged
- [x] All Wave 1 worktrees removed
- [x] Two worktrees created and removed post-merge
- [x] Stream A briefed and completed — PR #61 merged 2026-05-13
- [x] Stream B briefed and completed — PR #62 merged 2026-05-13

---

## DoD per stream

**Stream A — opens PR when:**
- [ ] `python -m pytest` passes (existing + new tests for /healthz, /readyz, structured logging)
- [ ] `curl http://localhost:8000/healthz` returns 200 with JSON body
- [ ] `curl http://localhost:8000/readyz` returns 200 when all 5 tool DBs are reachable; 503 when one isn't
- [ ] `docker build --target web .` succeeds with HEALTHCHECK pointing at `/healthz`
- [ ] At least one log line in production format is verifiable JSON with `request_id`, `user_email` (when authenticated), `path`, `method`, `status`
- [ ] PR description has 5-tool coverage row noting which tools' loggers were swapped
- [ ] Issues #7 and #33 close on PR merge

**Stream B — opens PR when:**
- [ ] `python -m pytest` passes (existing + new tests for DATA_DIR + WAL)
- [ ] `DATA_DIR=/tmp/portal-test python app.py` writes all SQLite DBs and uploaded files under `/tmp/portal-test/`
- [ ] `sqlite3 /tmp/portal-test/db/inventory.db "PRAGMA journal_mode"` returns `wal`
- [ ] Inventory QR PNGs appear under `DATA_DIR/generated/inventory/` (not `tools/inventory/static/`)
- [ ] `tools/inventory/db.py` and `tools/rf_chamber/db.py` exist with extracted schemas
- [ ] Print-request DB migration script idempotent; running twice doesn't break anything
- [ ] PR description has 5-tool coverage matrix
- [ ] Issues #2, #3, #9, #24, #47 close on PR merge

---

## Capacity plan

| Wave | Streams | Parallel agents | Est. wall-clock | Bottleneck |
|------|---------|-----------------|-----------------|------------|
| 2    | 2       | 2 Dev           | ~2 sessions     | Stream B (5-issue refactor) |
| 3    | 1-2     | 1-2 Dev         | ~1 session      | Audit log + small follow-ups |

**Total Sprint 3 footprint:** 7 issues closed in Wave 2 + 1-2 in Wave 3 (#46 audit log + carry-forward).

---

## Next step (Wave 3)

Wave 2 complete. Plan Wave 3: audit log (#46) + RBAC enforcement flip + Compose profiles + Dockerfile test-target split.

**Sprint 4 scope update (2026-05-13):** SQLAlchemy spike (#48 Equipment Checkout ORM layer) confirmed for Sprint 4 to de-risk Slice D-part2 (Postgres migration, Sprint 7). It joins Slice C (Celery + Redis + JSON API skeleton) in Sprint 4.
