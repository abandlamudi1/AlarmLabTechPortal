# Sprint 7 — Parallel Execution Plan

**Date:** 2026-05-14
**Author:** Stephen Nodder + AI planning assist (via `/plan-parallel-streams --milestone Next`)
**Milestone / focus:** Next milestone — Sprint 7 of the [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) 8-sprint engagement
**Anchor concerns:** Sprint 6 skill-infra friction follow-ups (F12 fallout: #119, #120, #121) + Slice 0 baseline (#45 unblock retry) + inventory API parity (#91)
**Goal:** Drain the Sprint 6 Wave 2 friction backlog (F12 — over-parameterization trap that surfaced during PR #117 review), retry the Slice 0 `qe-check` baseline that has been blocked since Sprint 3, and ship the small but long-deferred inventory-API/HTML parity fix (#91).

**Sprint capacity target:** 20–30 story points | Target waves: 1 | Target streams/wave: 5–8
**Actual scoped:** 4 issues, estimated ~8 story points across 3 streams (all Wave 1) — **Stream C dropped at kickoff** (see below)
**Under-load flag:** ⚠️ Below the 20-SP floor. Augmentation candidates from no-milestone backlog were reviewed (#98 OAS 3.0 upgrade, #103 architecture-guide design-system pattern, #115 FW snapshot reconcile) — only #91 was promoted by operator. Remaining candidates stay in backlog for the next milestone cycle once `Later` is groomed.

**Pre-flight verification (2026-05-15 kickoff):**
- ⛔ **Stream C dropped**: `python -c "import adc_github_sdk"` failed (`ModuleNotFoundError`). 3rd sprint with this blocker (Sprint 5, 6, 7). #45 stays in `Next` milestone; unblock requires action on `adc-quality/qe-repo-ai-assisted-guide` upstream.
- ✅ **Stream A field IDs discovered** for Project #23 — confirmed #121 root cause is classification (a): `create-issue/SKILL.md` references Project #26 field IDs. Correct values pasted into Stream A's brief below.

---

## Design decision: why parallel, what changed since Sprint 6

Sprint 6 closed today (2026-05-14) with `master` at `5e52b34`. Three of Sprint 6's PRs (most notably **#117** — the shared `skill-config.yml` refactor) generated follow-up friction that lives in [docs/wave-execute/friction-inventory.md](../wave-execute/friction-inventory.md) **F12** and the Wave 2 summary [docs/wave-execute/sprint-6-wave-2-2026-05-14.md](../wave-execute/sprint-6-wave-2-2026-05-14.md). Three of the four issues in this sprint (#119, #120, #121) are the operational drain of F12.

Sprint 7 is small (10 SP, 1 wave) on purpose: it cleans up F12 fallout with zero cross-stream coupling so the next planning cycle starts on a clean board. The single feature item (#91) is unrelated and runs in its own worktree.

---

## Pre-flight state

| Item | State | Notes |
|------|-------|-------|
| `master` tip | `5e52b34` | Sprint 6 fully merged: Wave 2 close-out (#118) on top of PR #117 (skill-config refactor) + Stream C |
| Sprint 6 fully closed | ✅ done | All Sprint 6 PRs merged; status tables green; #118 carries the wave-2 summary |
| Stale local branches | TBD | Run `git branch -r --list 'origin/*'` at kickoff; Sprint 6 worktrees should already be removed |
| Migration state | No in-flight migrations | `backend/migrations/` does not yet exist in this repo; Alembic adoption is Sprint 8 (Slice D-part2) |
| `adc_github_sdk` | ⚠️ **Verify before kickoff** | Same blocker that excluded #45 in Sprint 5 and Sprint 6. **Stream C cannot proceed if `python -c "import adc_github_sdk"` still fails.** |
| `.claude/skills/skill-config.yml` | ✅ present | Created by PR #117; #120 and #121 modify it further |
| `.claude/skills/create-issue/SKILL.md` | ✅ present | Field-ID inconsistency confirmed at lines 152, 163, 169, 181, 187, 199 (hardcoded `PVTSSF_lADODlOvwc4BPI7E*` — Project #26 IDs used against a Project #23 item) |

---

## Pre-flight AC Verification (Phase 0)

Verified by grep against `master` (commit `5e52b34`):

| Issue | Stated AC summary | Verified state | Classification |
|-------|-------------------|----------------|----------------|
| **#45** — qe-check baseline appended to `docs/guide-friction.md` under `## qe-check Baseline (Slice 0)` heading | No `qe-check Baseline` heading in master | **Open** — proceed if `adc_github_sdk` unblocks; otherwise re-block |
| **#119** — `AGENTS.md` has a `Centralization refactors` rule under Hard Rules | No `Centralization refactors` string in master `AGENTS.md` | **Open** — proceed |
| **#120** — `.claude/skills/skill-config.yml` header has `What to parameterize` guidance | No `What to parameterize` string in master skill-config.yml | **Open** — proceed |
| **#121** — `create-issue/SKILL.md` field IDs reference correct project | Hardcoded `PVTSSF_lADODlOvwc4BPI7E*` (Project #26 IDs) still present at lines 152, 163, 169, 181, 187, 199. Root cause **already confirmed** as classification (a) from the issue body — broken in master. | **Open** — proceed; investigation step in the issue body collapses to a verified bug fix |
| **#91** — `POST /api/v1/inventory/items` generates QR PNG via `set_qr_code()` | `set_qr_code()` is called only by HTML form path in `tools/inventory/inventory_app.py`; not called from `tools/api_v1/api_v1_app.py:269-286` | **Open** — proceed |

**Actionable Sprint 7 issues (5):** #45, #91, #119, #120, #121
**Shipped (0):** none
**Blocked (provisionally 1):** #45 pending `adc_github_sdk` install check at kickoff

---

## File Footprint Discovery (Phase 1)

### Per-issue footprints

| Issue | Path | Change | Reason |
|-------|------|--------|--------|
| **#45** | `docs/guide-friction.md` | MODIFY | Append `## qe-check Baseline (Slice 0)` section with `qe-check . --verbose` output |
| **#45** | External: `qe-check` CLI from `adc-quality/qe-repo-ai-assisted-guide` | RUN-ONLY | Operator-driven; no repo file change. Failures (any P0) escalate to new issues — separate scope. |
| **#91** | `tools/api_v1/api_v1_app.py` | MODIFY | After `_inventory_db.add_item()` in `create_inventory_item()` (~lines 269-286), generate QR PNG and call `_inventory_db.set_qr_code()` — mirror the HTML flow |
| **#91** | `tools/inventory/inventory_app.py` | MODIFY (optional refactor) | Extract the qrcode-generation block into a shared helper if duplication is meaningful; otherwise inline call is acceptable |
| **#91** | `tests/test_api_v1.py` | MODIFY | New tests: POST creates item AND a QR row is present; uses `tmp_path` fixture for `DATA_DIR/generated/inventory/` |
| **#91** | `tests/conftest.py` | READ-ONLY-VERIFY | Confirm the existing `tmp_path` fixture (line ~19) already creates `generated/inventory/`; no edit expected |
| **#119** | `AGENTS.md` | MODIFY | Add `Centralization refactors` paragraph under Hard Rules; one worked example (`PVT_kwDODlOvwc4BPI7E` vs `PVT_kwDODlOvwc4BOhf-`); link to F12 in friction-inventory.md |
| **#120** | `.claude/skills/skill-config.yml` | MODIFY | Append `What to parameterize` note to preamble comment block (top of file, before `repo:` key) |
| **#121** | `.claude/skills/create-issue/SKILL.md` | HEAVY_MODIFY | Replace hardcoded `PVTSSF_lADODlOvwc4BPI7E*` field IDs with `$CONFIG.github.priority_field_id` / `size_field_id` / `status_field_id` references — but **only after** discovering the correct Project #23 field IDs via the GraphQL query in the issue body |
| **#121** | `.claude/skills/skill-config.yml` | MODIFY | Add new `priority_field_id` + `size_field_id` keys (with Project #23 option-IDs nested as `priority_options:` and `size_options:`); also add a header comment noting which field-IDs belong to which project board |

### Implicit scope surfaced

- **#91** — sub-agent verified that `_inventory_db.set_qr_code()` already exists; no DB-layer changes needed; no migration needed; no config changes needed
- **#121** — likely surfaces correct Priority/Size option IDs for Project #23 (different from the Project #26 option IDs documented in lines 156-160 and 173-178 of `create-issue/SKILL.md`). These belong in `skill-config.yml` alongside the existing `status_options` block.
- **#119** + **#120** — both stem from F12 but touch different files (AGENTS.md vs skill-config.yml). The F12 root-cause link in #120's preamble note should reference #119's AGENTS.md rule for canonical guidance — soft documentation linkage, not a file overlap.

### Migration conflict pre-check (Step 1.3)

**No migrations required in Sprint 7.** None of the streams modify `backend/migrations/` (which doesn't exist yet) or `tools/inventory/db.py` schema.

---

## File Overlap Matrix (Phase 2)

|  | A (#120, #121) | B (#119) | C (#45) | D (#91) |
|--|--|--|--|--|
| **A** | — | 0% | 0% | 0% |
| **B** |  | — | 0% | 0% |
| **C** |  |  | — | 0% |
| **D** |  |  |  | — |

**Zero file overlap between any stream pair.** Stream A intentionally combines #120 and #121 because both touch `.claude/skills/skill-config.yml` (#120 the preamble comment, #121 adds new YAML keys). All other streams target a disjoint surface.

### Shared files within Stream A (informational)

| File | Issues | Risk |
|------|--------|------|
| `.claude/skills/skill-config.yml` | #120, #121 | LOW — #120 edits preamble comment; #121 adds new YAML keys below `github:` map. Different regions; same agent handles both within one worktree to avoid serialization. |

---

## Stream Formation & Wave Plan (Phase 3)

### Stream A: Skill-config + create-issue field-ID cleanup (#120, #121)

- **Issues**: #120 (`What to parameterize` note in skill-config.yml header), #121 (create-issue field-ID inconsistency: investigate + fix)
- **Why grouped**: both touch `.claude/skills/skill-config.yml`. Combining them in one worktree avoids serialization on the shared file and lets the agent reason about the YAML preamble and the new field-ID keys together.
- **Total SP**: ~4 (S + S)
- **Worktree**: `../lab-tech-portal-now-A-skill-config-fixes`
- **Branch**: `fix/now-A-skill-config-fixes`
- **Internal ordering**:
  1. #121 step 1 — ✅ **already verified at kickoff**. Project #23 field IDs and option IDs (do NOT re-query; use these directly):
     ```yaml
     # Project #23 — paste into skill-config.yml under github: map
     priority_field_id: PVTSSF_lADODlOvwc4BOhf-zg9M4IE
     priority_options:
       p0: e8e3f65a
       p1: ef2fb57a
       p2: 03271471
       p3: f80af26b
       p4: 303336e7   # NEW vs Project #26 (P4 did not exist there)
     size_field_id: PVTSSF_lADODlOvwc4BOhf-zg9M4II
     size_options:
       xs: 0beb35cf
       s: 6236dd70
       m: 228d3b49
       l: 3aaa4f40
       xl: 4a4ae26b
     ```
     Note: `status_field_id` and `status_options` already exist in `skill-config.yml` under `github:` and are correct for Project #23. Do not duplicate.
  2. #121 step 2 — add the new keys above to `skill-config.yml` under the `github:` map; update the preamble header comment to call out which IDs belong to Project #23 vs Project #26 (existing `defer_priority_field_id` / `defer_size_field_id` stay for `defer-pr-comments`).
  3. #121 step 3 — update `create-issue/SKILL.md` lines 152, 163, 169, 181, 187, 199 to reference `$CONFIG.github.priority_field_id` / `size_field_id` / `status_field_id` and the new option-ID nested keys.
  4. #120 — append the `What to parameterize` note to the preamble comment block of `skill-config.yml`.
  5. Verify by mentally re-resolving every `$CONFIG.*` reference in `create-issue/SKILL.md` against the new YAML.
- **Splits this PR may need**: none expected (<200 lines)

### Stream B: AGENTS.md centralization-refactors rule (#119)

- **Issues**: #119
- **Why solo**: AGENTS.md is the only file touched; no overlap with any other stream
- **Total SP**: ~1 (XS)
- **Worktree**: `../lab-tech-portal-now-B-agents-md-rule`
- **Branch**: `docs/now-B-agents-md-centralization-rule`
- **Internal ordering**: single edit — add the rule, cite F12 in friction-inventory.md, include the worked example from the issue body.

### Stream C: qe-check Slice 0 baseline (#45)

- **Issues**: #45
- **Why solo**: only touches `docs/guide-friction.md`; depends on an external CLI install (`qe-check` from `adc-quality/qe-repo-ai-assisted-guide`)
- **Total SP**: ~2 (S)
- **Worktree**: `../lab-tech-portal-now-C-qe-check-baseline`
- **Branch**: `chore/now-C-qe-check-baseline`
- **Pre-flight gate (BLOCKING)**: at kickoff, verify `python -c "import adc_github_sdk"` succeeds. If it fails, **re-block #45** and remove Stream C from this sprint — same outcome as Sprint 5 and Sprint 6. File a new tracker issue against `adc-quality/qe-repo-ai-assisted-guide` if one does not already exist.
- **Internal ordering**:
  1. Install `qe-check` from local guide repo.
  2. Run `qe-check . --verbose` and capture stdout.
  3. Append `## qe-check Baseline (Slice 0)` section to `docs/guide-friction.md` with the date + verbatim output.
  4. For each P0 failure (if any), file a new GitHub issue via `/create-issue`.

### Stream D: Inventory API QR code parity (#91)

- **Issues**: #91
- **Why solo**: backend code change, fully disjoint from skill/docs streams
- **Total SP**: ~3 (S)
- **Worktree**: `../lab-tech-portal-now-D-inventory-qr`
- **Branch**: `feat/now-D-inventory-qr-on-post`
- **Internal ordering**:
  1. Read `tools/inventory/inventory_app.py` HTML form handler — note the qrcode.make + set_qr_code call pattern.
  2. Mirror it inside `tools/api_v1/api_v1_app.py:create_inventory_item()` after `_inventory_db.add_item()`.
  3. Decide on extract-vs-inline (operator preference: prefer extraction into a small helper if duplication exceeds ~8 lines).
  4. Add tests to `tests/test_api_v1.py` using the existing `tmp_path` fixture (verified in conftest.py line 19).
  5. Run the inventory test suite locally before pushing.

### Dependency graph between streams

```
Stream A ──┐
Stream B ──┤
Stream C ──┼──► All independent; all Wave 1; no cross-stream blockers
Stream D ──┘
```

**No Wave 2.** All four streams ship into the same wave.

### Cross-stream integration risks (Phase 3.4 critic check)

| Concern | Found | Mitigation |
|---|---|---|
| Import-chain coupling | None — none of these streams import from each other's targets | n/a |
| Shared test fixtures | None — only Stream D edits tests; conftest.py is read-only-verify | n/a |
| Runtime coupling | None — skill files are agent-time only; #91 is backend-only | n/a |
| Config coupling | None — #121 adds new `skill-config.yml` keys that no other stream consumes during this sprint | n/a |
| Frontend shared state | None — no frontend changes in this sprint | n/a |
| Soft documentation linkage | #119 and #120 both stem from F12 | Document the cross-reference inside the respective issue bodies / PR descriptions; no mechanical conflict |

---

## Agent Team Allocation (Phase 4)

Following [docs/AGENT-MODEL-SELECTION.md](../AGENT-MODEL-SELECTION.md).

| Stream | Classification | Dev model | QE model | Rationale |
|--------|---------------|-----------|----------|-----------|
| **A** (#120, #121) | Standard | Sonnet | Haiku | Multi-file edit with a discovery step (GraphQL query for correct field IDs). Sonnet for the judgment around YAML key placement and the existing/new project boundary |
| **B** (#119) | Trivial | Haiku | Haiku | Single doc edit, fully specified by the issue body's example |
| **C** (#45) | Trivial-but-environmental | Haiku | Haiku | Tooling + doc append. Operator-driven CLI step makes this gated; the actual repo edit is mechanical |
| **D** (#91) | Standard | Sonnet | Haiku | Real backend feature touching API + service + tests. Pattern exists (HTML form path) so model has a template to mirror |

**Shared roles:**
- **Architect** (Opus, one-shot) — runs Phase 2 overlap recheck against current master at kickoff; confirms zero-overlap claim and re-validates Stream C's blocker status
- **Critic** (Haiku, pre-PR gate per stream) — runs the pre-PR checklist before each Dev agent opens its PR

### Line-budget enforcement

Each agent prompt MUST include the **600-line PR cap** clause (additions + deletions). All four streams are expected well under 600 lines; no pre-splits planned.

| Stream | Est. lines | Pre-split? |
|---|---:|---|
| A | ~120 | no |
| B | ~30 | no |
| C | ~40 (mostly appended qe-check output) | no |
| D | ~150 | no |

### Capacity plan

| Wave | Streams | Parallel Dev agents | Parallel QE agents | Est. duration | Bottleneck |
|------|---------|--------------------:|-------------------:|---------------|------------|
| 1    | 4 (A, B, C, D) | 4 | 4 | ~1.5h | Stream A (multi-step + GraphQL discovery) |

---

## Conflict-cutting rules

These are inherited project conventions; do not modify.

1. **Rebase daily**: `git fetch origin && git rebase origin/master` on every active worktree
2. **Migration numbering check before branching**: `ls backend/migrations/versions/ | tail -1` (no migrations expected this sprint, but the habit stays)
3. **Overlap check before promoting any new branch to parallel**:
   ```bash
   comm -12 <(gh pr diff NNN --name-only | sort) <(git diff master --name-only | sort)
   ```
   If overlap > 30%, wait for the first PR to merge or merge the branches.
4. **Push review fixes to the PR being reviewed** — never sidecar them onto another active branch
5. **PR titles require `QENG-16846:` prefix** and conventional commit scope
6. **One concern per PR** even within a worktree — if a stream grows past ~600 line delta, split into separate PRs
7. **Worktree cleanup**: `git worktree remove <path>` immediately after PR merge

---

## Status tracking table

Update this table as Wave 1 progresses. `sprint-close --batch` filters completion checks by the `Wave` column.

| Wave | Stream | State | Branch | PR | Depends on | Blockers |
|------|--------|-------|--------|----|------------|----------|
| 1 | A (#120, #121) | **in-progress** | `fix/now-A-skill-config-fixes` | — | — | none |
| 1 | B (#119) | **in-progress** | `docs/now-B-agents-md-centralization-rule` | [#128](https://github.com/adc-quality/lab-tech-portal/pull/128) | — | none |
| 1 | ~~C (#45)~~ | ⛔ DROPPED 2026-05-15 | — | — | — | `adc_github_sdk` ModuleNotFoundError (3rd consecutive sprint blocked) |
| 1 | D (#91) | **in-progress** | `feat/now-D-inventory-qr-on-post` | — | — | none |

---

## Pre-flight checklist (do once before spawning agents)

- [ ] `git checkout master && git pull` — clean tree on master
- [ ] `git worktree list` — verify Sprint 6 worktrees have been removed; clean up any stragglers
- [ ] `git branch -r --list 'origin/feat/*' 'origin/fix/*' 'origin/chore/*' 'origin/docs/*'` — confirm no in-flight branches with overlapping footprints
- [ ] Stream C gate: `python -c "import adc_github_sdk"` — if this fails, **drop Stream C from this wave** and file/update the blocker tracker
- [ ] Confirm Docker services healthy: `docker compose ps`
- [ ] For Stream A, pre-run the GraphQL field-discovery query so the correct Project #23 Priority/Size field IDs and option IDs are pasted into the Dev agent's brief:
  ```bash
  gh api graphql -f query='query { node(id: "PVT_kwDODlOvwc4BOhf-") { ... on ProjectV2 { fields(first: 20) { nodes { ... on ProjectV2SingleSelectField { id name options { id name } } } } } } }'
  ```
- [ ] Architect agent runs one-shot overlap recheck against current master
- [ ] Each Dev agent gets: stream row + issue bodies + this plan as context

---

## Notes on under-load (skill capacity guidance)

This sprint is materially below the 20–30 SP target. Three forces are at play:

1. **Sprint 6 was big** (~21 SP across 8 streams + 2 waves) — Sprint 7 inherits only the small friction follow-ups it produced.
2. **`Later` milestone is empty** — no pre-groomed feed into `Next` aside from the four no-milestone candidates surfaced.
3. **Operator chose to keep scope tight** — preferred to defer #98 (OAS 3.0 upgrade) and #115 (FW snapshot reconcile) rather than pack the wave.

Recommended follow-up: run `/backlog-groom` after Sprint 7 merges to repopulate `Next` from the no-milestone backlog and from the Slice G/H pre-stubs implied by `docs/CLEANUP_PLAN.md`. Target Sprint 8 to return to 20+ SP across 2 waves.

---

## Related docs

- `docs/workflows/multi-agent-worktree-workflow.md` — worktree mechanics
- `docs/workflows/worktree-lessons-learned.md` — why concern-based > per-issue grouping
- `docs/workflows/merge-and-review-workflow.md` — PR merge strategy
- `docs/workflows/sprint-skill-chain.md` — full skill chain orchestration
- `docs/AGENT-MODEL-SELECTION.md` — model tier allocation
- `docs/wave-execute/friction-inventory.md` — F12 root-cause analysis (drives #119, #120, #121)
- `docs/wave-execute/sprint-6-wave-2-2026-05-14.md` — origin of the F12 follow-ups
