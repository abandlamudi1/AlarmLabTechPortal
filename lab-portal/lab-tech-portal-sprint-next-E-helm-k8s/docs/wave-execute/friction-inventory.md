# Wave Execute Friction Inventory

Recurring friction patterns observed across waves. Each entry tracks the pattern from discovery → mitigation → closure. The `Active` section is auto-surfaced during Phase 0 of `/wave-execute` so future waves carry forward the lessons.

## Status legend

- **Active** — pattern observed ≥1 times, no mitigation in place yet
- **Mitigated** — fix applied (rule, tooling, skill change); watching to confirm it sticks
- **Closed** — no recurrence in ≥3 consecutive waves; safe to ignore

## Threshold rules for issue auto-creation

- **First observation**: surface in the wave summary as a proposed issue (checkbox the human ticks)
- **Second observation** (cross-wave): auto-create issue with label `wave-friction` at Phase 5; human still reviews
- **Third observation**: escalate — block the next wave until a rule or tool change is proposed

---

## Active

### F04 — Celery task autodiscovery not configured

- **Pattern**: Dev agent adds a `tasks/` module using `@shared_task` but does not add it to `include=["tasks.module"]` in the `Celery()` constructor in `celery_app.py`. Tasks register fine in tests (module imported directly) but fail at runtime on the worker with "Received unregistered task of type".
- **First observed**: Sprint 5 Wave 2 (2026-05-13) — Stream E (PR #96) added `tasks/periodic.py` without updating `include=` in `make_celery()`.
- **Recurrence count**: 1
- **Mitigation**: Copilot caught it in Round 1. Fixed in PR #96. Proposed rule: add to AGENTS.md and celery_app.py comment — "When adding a new tasks module, add it to the `include=` list in `make_celery()`."
- **Status**: Active — rule not yet written

### F05 — `crontab()` without explicit hour/minute fires every minute

- **Pattern**: `crontab(day_of_week=N)` without `hour` and `minute` defaults to `hour="*", minute="*"` — the schedule fires 1440× per day rather than once. Celery's crontab matches all fields that are not specified.
- **First observed**: Sprint 5 Wave 2 (2026-05-13) — Stream E (PR #96) weekly cleanup task.
- **Recurrence count**: 1
- **Mitigation**: Copilot caught it in Round 1. Fixed by adding `hour=0, minute=0` explicitly. Proposed: document in a Celery patterns doc.
- **Status**: Active — doc not yet written

### F06 — Schema migration guard placed in task hot-path instead of DB init

- **Pattern**: A task function calls `_ensure_columns()` (or similar) on every invocation to defensively handle a column added by a parallel stream. This puts a `PRAGMA table_info` + conditional `ALTER TABLE` on the hot path of every task run.
- **First observed**: Sprint 5 Wave 2 (2026-05-13) — Stream G (PR #97) `_update_task_status()` called `_ensure_task_columns()` each time.
- **Recurrence count**: 1
- **Mitigation**: Copilot classified as PERFORMANCE in Round 1. Fixed by caching the check with a module-level flag (`_COLUMNS_VERIFIED`). Proposed rule: schema checks belong in `_migrate_schema()` at DB init time.
- **Status**: Active — rule not yet written

### F07 — Wave under-load: single-stream wave when compatible issues were available

- **Pattern**: A wave executes with only 1–2 streams when several "Next" milestone issues had no file overlap with the wave's streams and no blocking dependencies. Sprint velocity drops to a fraction of demonstrated capacity.
- **First observed**: Sprint 5 Wave 3 (2026-05-14) — 1 stream ran (#18) when issues #89, #90, #99, #100 were open and compatible.
- **Recurrence count**: 1
- **Root cause**: Two contributing factors: (a) sprint plan fixed at wave-1 kickoff, not updated as new SCOPE issues were created mid-sprint; (b) wave-execute had no under-load detection or backlog-augmentation step.
- **Mitigation**: Added Step 0.3.5 to `wave-execute` SKILL.md (under-load check + auto-add in `--auto` mode) and Phase 1.1.5 to `plan-parallel-streams` SKILL.md (sprint capacity check + backlog augmentation). Tracked in issues #104 and #105.
- **Status**: Active — skill changes applied but untested in a live sprint yet

### F12 — Over-parameterization during centralization refactor

- **Pattern**: When centralizing constants into a shared config file, the Dev agent collapses *distinct* upstream values onto the same new `$CONFIG.*` key. The agent's "grep for hardcoded literals and replace" approach treats visually-similar literals as fungible, even when they reference different entities (different project boards, different field IDs, different orgs). Three sub-patterns observed in a single wave:
  1. Two distinct GitHub Project boards (Project #23 main + Project #26 deferred-items) collapsed onto one `$CONFIG.github.project_id`, breaking `defer-pr-comments` (would silently write deferred-item state to the wrong board / wrong field).
  2. Hardcoded `organization(login: "adc-quality")` missed in 2 of 14 files — agent matched on shell-variable form (`REPO_OWNER=...`) but skipped inline GraphQL string literals with the same value.
  3. Markdown link **text** parameterized to `$CONFIG.foo` while the link **target** stays literal — the read-then-resolve mechanism doesn't substitute at markdown-render time, so the rendered link displays the placeholder.
- **First observed**: Sprint 6 Wave 2 (2026-05-14) — Stream C (PR #117), `.claude/skills/skill-config.yml` introduction. Copilot caught all four instances in round 1.
- **Recurrence count**: 1
- **Root cause**: The agent's self-test step ("grep for hardcoded literals to confirm replacement") doesn't differentiate between callsites that point to the *same* logical entity vs. coincidentally-similar values pointing to *different* entities. There's also no rule about which surfaces (markdown link text, narrative prose, code/query parameters) should and should not be parameterized.
- **Mitigation**: Fixed in commits `bc91869` + `9d5e4c0` (PR #117) — added `github.org`, `defer_project_number`, `defer_project_id`, `defer_priority_field_id`, `defer_size_field_id` to `skill-config.yml`; reverted parameterized markdown-link text back to literal in two files. Proposed AGENTS.md / Dev-agent prompt rule: *"When replacing literal X with `$CONFIG.foo` in a centralization refactor, first group all callsites of X by the entity they reference. Introduce one `$CONFIG.*` key per distinct entity. Do not parameterize markdown link text — only command/query parameters."*
- **Watch for**: Future centralization-style refactors (env-var unification, logging-config consolidation, secret-store rollout). Same trap.
- **Status**: Mitigated (2026-05-15) — AGENTS.md `Centralization refactors` rule shipped in PR #128 (closes #119); `What to parameterize` corollary appended to skill-config.yml preamble in PR #130 (closes #120); Project #23 vs #26 field IDs separated in PR #130 (closes #121).

### F13 — adc_github_sdk install path documented but pip cannot resolve git+ deps via deprecated dependency_links

- **Pattern**: `qe-check` CLI from `qe-repo-ai-assisted-guide` cannot be installed because `setup.py` parses git+ URLs from `requirements.txt` into bare package names (`adc-github-sdk`, `adc-confluence-sdk`, `ms-teams-sdk`, `qe-sprint-sdk`) plus `dependency_links` entries. Modern pip (≥18) ignores `dependency_links`, then fails to resolve those bare names from PyPI.
- **First observed**: Sprint 5 / Sprint 6 (as `adc-jira-sdk` blocker), Sprint 7 (as broader `adc-github-sdk` blocker after `adc-jira-sdk` was installed manually).
- **Recurrence count**: 3 (Sprint 5, 6, 7 — same root cause, different surface SDK)
- **Root cause**: Upstream `setup.py` uses deprecated dependency_links instead of PEP 508 direct references (`pkg @ git+https://…`).
- **Mitigation**: None upstream yet. Stream C dropped each sprint. Install recipe + failure mode persisted to user-memory (`reference_adc_github_sdk_and_qe_check.md`).
- **Watch for**: Any future portal work that depends on qe-check or any of the ADC internal SDKs declared in `qe-repo-ai-assisted-guide/requirements.txt`.
- **Status**: Active — recurrence count = 3 → BLOCKING per Wave 7+ until upstream is patched. **Sprint 8 next-actions** should include filing the patch issue against `adc-quality/qe-repo-ai-assisted-guide`.

### F14 — Inline duplication of QR helper across HTML + JSON-API paths flagged despite explicit prompt allowance

- **Pattern**: Stream D Dev agent kept a 4-line QR-generation block inline (per operator preference encoded in the kickoff prompt: "≤8 lines inline is fine"). Copilot round-1 review flagged the duplication regardless, citing prior layout change in #47 as proof of drift risk.
- **First observed**: Sprint 7 Wave 1 (2026-05-15) — Stream D (PR #129), `tools/api_v1/api_v1_app.py` mirroring `_qr_dir()` from `tools/inventory/inventory_app.py`.
- **Recurrence count**: 1
- **Root cause**: Operator preference (small duplication acceptable) is at odds with Copilot's default ("any duplication risks drift"). The friction is irreducible — both are defensible positions.
- **Mitigation**: Tracked the refactor in #131 (Icebox); inline implementation merged in PR #129. SCOPE reply on the Copilot comment cites the operator preference + the tracking issue.
- **Watch for**: Any future stream where kickoff prompt explicitly allows inline duplication — expect Copilot to flag and need a SCOPE reply.
- **Status**: Active — no skill-level mitigation needed (the friction is operator-policy vs. Copilot-default tension, not a bug)

### F15 — PyYAML 1.1 octal coercion silently corrupts all-digit option IDs

- **Pattern**: A YAML scalar that is all digits with a leading zero (e.g. `p2: 03271471`) is parsed by `yaml.safe_load` as an octal integer (`881465`), not a string. Downstream code that resolves `$CONFIG.github.priority_options.p2` and passes it as a GraphQL `singleSelectOptionId` then sends the wrong value to GitHub.
- **First observed**: Sprint 7 Wave 1 (2026-05-15) — Stream A (PR #130), `.claude/skills/skill-config.yml` `priority_options.p2`.
- **Recurrence count**: 1
- **Root cause**: PyYAML defaults to YAML 1.1 parsing, where leading-zero all-digit scalars are octal. The risk is invisible at write-time and only surfaces when the parsed value is used.
- **Mitigation**: All option IDs across priority/size/status maps quoted defensively in PR #130; explanatory comment added above `status_options:`.
- **Watch for**: Any future skill-config addition where option IDs / single-select IDs are stored. If an ID is all digits, quoting is mandatory; if it contains letters, quoting is optional but stylistically consistent.
- **Status**: Active — fix shipped but no preventive rule. Sprint 8 proposed action: add a Hard Rule or a tiny pre-commit YAML-type check.

### F08 — XSS sink in async polling JS (innerHTML with server-sourced error text)

- **Pattern**: Async polling JS blocks use `element.innerHTML = html` where `html` is a string built from `data.error` or similar server-sourced fields. Celery exception messages can contain arbitrary text from upstream services (e.g. Jira API responses), making this a script-injection sink.
- **First observed**: Sprint 5 Wave 3 (2026-05-14) — PR #102, both `print_request_detail.html` and `jira_import.html`.
- **Recurrence count**: 1
- **Root cause**: Dev agent used innerHTML as a convenient way to insert styled content. The XSS risk of server-controlled strings rendered as HTML was not called out in the agent prompt.
- **Mitigation**: Fixed in commit `a5eb89a` (PR #102) — replaced innerHTML with `textContent`/DOM construction. Proposed AGENTS.md hard rule: "Never use innerHTML to insert server-sourced data. Use textContent or DOM element construction."
- **Status**: Active — AGENTS.md rule not yet written; next UI stream will face the same footgun

---

## Mitigated

### F01 — Stale callers after DB-layer attribute move

- **Pattern**: A PR moves `module.X` to `new_module.Y_PATH` (or renames an exported attribute). Callers in `app.py`, `conftest.py`, or service modules aren't updated. The `AttributeError` is masked by Python dict-evaluation order (hits the first failing attr and short-circuits), so test failures appear one at a time across waves.
- **First observed**: Sprint 3 Wave 3 (2026-05-13) — PR #62 (Slice D-part1) moved `tools.inventory.inventory_app.DB` to `tools.inventory.db.DB_PATH` but `app.py`'s `readyz` was not updated. Same again for `rf_chamber`. Both Stream A (PR #69) and Stream B (PR #67) hit it independently.
- **Recurrence count**: 1 (within a single wave, surfaced 2× via dict-eval masking)
- **Mitigation**:
  - `AGENTS.md` hard rule: remove dead imports immediately when replacing a module attribute (PR #70)
  - `docs/workflows/pr-review-tiered.md` never-soften rule for stale callers after DB-layer move (PR #70)
- **Watch for**: Slice D-part2 (Postgres migration) — SQLAlchemy model + Alembic baseline is the next likely trigger
- **Status**: Mitigated (2026-05-13)

### F02 — CI poll premature exit on empty-string `conclusion`

- **Pattern**: `gh pr view ... --jq '.statusCheckRollup[] | .conclusion // .status'` short-circuits when `conclusion` is `""` (empty string, not null) during a check's in-progress state. The `//` operator treats `""` as truthy and skips the `.status` fallback, so the poll reports the check as done before it actually finishes.
- **First observed**: Sprint 3 Wave 3 (2026-05-13)
- **Recurrence count**: 1 (multiple polls in the same wave)
- **Mitigation**: skill updated to use `.status` directly with `select(.name != null)` for phantom-check filtering. Recorded in Known Fragilities section of `wave-execute/SKILL.md`.
- **Status**: Mitigated (2026-05-13)

### F03 — Dev agents add new import but leave old one in place

- **Pattern**: When refactoring imports, the agent adds the new import alongside the old one without removing the stale alias. Coexistence is harmless at runtime (dead import) but creates merge conflicts when another stream removes the stale import in the same file.
- **First observed**: Sprint 3 Wave 3 (2026-05-13) — Stream A added `tools.inventory.db as _inventory_db` alongside `tools.inventory.inventory_app as _inventory_module`. Conflict surfaced during rebase onto post-Wave-3 master.
- **Recurrence count**: 1
- **Mitigation**: AGENTS.md rule (same as F01) with explicit `grep -r "_old_module"` self-check command. Dev agent prompt template (sprint-kickoff) needs an additional line — see follow-up issue.
- **Status**: Mitigated — pending follow-up to add the explicit instruction to sprint-kickoff's prompt template

---

## Closed

*(none yet — entries promote here after 3 consecutive friction-free waves)*
