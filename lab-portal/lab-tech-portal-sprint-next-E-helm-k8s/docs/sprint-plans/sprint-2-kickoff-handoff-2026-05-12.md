# Sprint 2 — Kickoff Handoff Prompt

> **Purpose:** drop the contents of this file into the next Claude Code session to bootstrap the Sprint 2 Wave 1 kickoff with full context but minimal token spend.
>
> **Generated:** 2026-05-12 at end of the design session that produced [sprint-2-execution-plan-2026-05-12.md](sprint-2-execution-plan-2026-05-12.md) and the `/guide-friction-sync` skill.

---

## Copy-paste prompt for the new session

```
## Sprint 2 kickoff — lab-tech-portal, Wave 1

You are picking up where the design session of 2026-05-12 left off. The Sprint 2 parallel execution plan and the /guide-friction-sync skill design were both produced and shipped via PR (see "State of the repo" below). Your job now is to kick off Wave 1.

### State of the repo
- `master` is current. The Sprint 2 design PR for the plan + .claude/ infra + guide-friction-sync skill should be merged before kickoff (check `gh pr list` if unsure).
- PR #43 (Slice 0b deferred init) is already merged; app.py is unblocked.
- The latest changelog and merged PRs are in [changelogs/](../../changelogs/) and `git log --oneline master | head -10`.

### What to read first (in this order)
1. **[docs/sprint-plans/sprint-2-execution-plan-2026-05-12.md](sprint-2-execution-plan-2026-05-12.md)** — the canonical plan. Three streams (A/B/C), stream definitions, file-overlap matrix, status table, DoD per stream.
2. **[AGENTS.md](../../AGENTS.md)** — hard rules, 5-tool coverage discipline, JIRA prefix convention (QENG-16846).
3. **[docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) §Slice A, §Slice G-part1, §Slice H** — the engagement-level context for what each slice means.

### Three streams to spawn (Wave 1, all parallel — no inter-stream blocking except for one soft edge noted below)
| Stream | Branch | Worktree | Issues | Anchor |
|--------|--------|----------|--------|--------|
| A — Slice A auth | `feature/sprint-2-slice-a-auth` | `../lab-tech-portal-sprint-2-slice-a` | #6, #11, #36, #44 | app.py + config.py + 5-tool template rollout |
| B — Slice G-part1 Docker | `feature/sprint-2-slice-g-part1-docker` | `../lab-tech-portal-sprint-2-slice-g-part1` | #5, #19, #20, #22, #23, #25 | wsgi.py + Dockerfile + compose + CI |
| C — Docs + baseline | `feature/sprint-2-docs-baseline` | `../lab-tech-portal-sprint-2-docs-baseline` | #38, #50, #45 | architecture.md + DOCKER_RUNBOOK.md + runbook-k8s.md + guide-friction.md |

### Critical callouts (do NOT lose these — they came from pre-flight discovery in the design session)
1. **Issues #6 and #11 are PARTIAL, not Open.** `config.py:97-117` already defines the env vars (#6) and `config.py:181-249` already has validate_config/init_app (#11). Stream A is **wiring**, not building. Brief the Stream A Dev agent: "consume existing env vars; do NOT re-define them in config.py".
2. **Legacy hard-delete PIN hard rule.** Stream A must remove the literal PIN value from source. Move it to env var `SYSTEM_LOCATOR_DELETE_PIN`. Verify by greping `tools/system_locator/` and `services/` for any 4-digit string-literal and confirming only the env-var lookup remains. Do NOT commit the legacy literal anywhere — including in plan docs, handoff prompts, or commit messages.
3. **RBAC ships warn-only.** Logs denials, returns 200. Enforcement flips in Sprint 3.
4. **README.md ownership.** Stream B does NOT edit `README.md`. It drafts a Docker-quickstart blurb in its PR description; Stream C lifts that into README. Soft edge mitigation.
5. **requirements.txt soft edge.** Stream A adds Flask-WTF + Flask-Limiter. Stream B prefers `requirements-prod.txt` (new file) for Gunicorn. If both touch `requirements.txt`, conflicts are additive — accept both.
6. **Stream C dependency.** Stream C agent should not finalize `docs/DOCKER_RUNBOOK.md` until Stream B drafts `docker-compose.yml`. Inside Stream C: do #45 baseline → start #38 (architecture diagram) → wait for Stream B PR → finish #38 (runbook commands) → ship #50 k8s skeleton.

### Action: invoke /sprint-kickoff
Run `/sprint-kickoff` (or local equivalent) pointing at the plan path:
```
/sprint-kickoff docs/sprint-plans/sprint-2-execution-plan-2026-05-12.md --wave 1
```
The skill should:
1. Create the three worktrees
2. Generate per-agent prompts from each stream row, incorporating the critical callouts above
3. Launch the Dev agents in parallel (Sonnet for A and B, Haiku for C — see plan §Agent team allocation)
4. Optionally spawn a one-shot Architect (Opus) for a final overlap-check against current master before the Devs start

### Pattern citation convention (for Stream A new code)
```python
# Pattern: docs/patterns/auth/multi-mode-auth.md (qe-architecture-ai-assisted-guide @ <SHA>)
```
The SHA pins to the architecture-guide commit at branch creation. If unclear, append an entry to [docs/guide-friction.md](../guide-friction.md) and continue.

### Memory entries relevant to this kickoff
- `feedback-guide-friction-workflow` — how the friction → tracking pipeline works
- `reference-guide-project-boards` — project routing per guide repo
- `reference-cleanup-artifacts` — where CLEANUP_PLAN, guide-friction, AGENTS.md live
- `project-cleanup-engagement` — the 8-sprint engagement context

### Deferred items (do NOT pull into Sprint 2)
- `/guide-friction-sync` skill is **DRAFT**, not operational. Don't invoke it. It's design-complete; build-out is a separate workstream tracked in the "On promotion to live state" checklist of its SKILL.md.
- Handoff-skill design (proposed by Stephen on 2026-05-12) — sketch this as a follow-on after Sprint 2 Wave 1 PRs are in flight, not now.
- Issue #52 (file guide-friction PRs from the log) — Slice H, much later. Don't include in Sprint 2.

### When something goes wrong
- If overlap discovery from the Architect one-shot disagrees with the plan, **trust the Architect** (it's reading current master, the plan was a snapshot). Adjust stream definitions before spawning Devs.
- If a Dev agent's diff approaches 600 lines, invoke the pre-split rule from §Line-budget enforcement in the plan.
- If Stream A's CSRF template rollout (5 tools) bloats the diff, split into PR1 (backend) + PR2 (templates + RBAC) on the same branch.
```

---

## Why this handoff file exists

Stephen's preference (2026-05-12): when context is the limiting factor, write a starter prompt for the next session capturing (a) status, (b) complete vs in-progress, (c) next steps, (d) blockers. This file is that prompt for the Sprint 2 kickoff transition.

**A future handoff skill** (separate workstream, sketched after Sprint 2 Wave 1 kickoff) will generate this format automatically from git/PR state + a short interview, replacing the hand-written version.

---

## End-of-design-session checklist (already done before this file was written)

- [x] Sprint 2 plan written: [sprint-2-execution-plan-2026-05-12.md](sprint-2-execution-plan-2026-05-12.md)
- [x] `/guide-friction-sync` skill designed: [.claude/skills/guide-friction-sync/SKILL.md](../../.claude/skills/guide-friction-sync/SKILL.md)
- [x] All 4 skill TBDs resolved (project routing #8, Pattern+SourceRepo grouping, 6-value vocab, PR-for-review push behavior)
- [x] Memory updated: `reference-guide-project-boards`, `feedback-guide-friction-workflow`
- [x] PR opened for this session's work (link will appear after `gh pr create` completes)
