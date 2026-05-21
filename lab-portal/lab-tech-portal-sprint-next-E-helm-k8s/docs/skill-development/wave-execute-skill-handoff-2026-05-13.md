# `/wave-execute` skill — design handoff

> **Purpose:** Drop the contents of this file into a fresh Claude Code session to design and build the `/wave-execute` skill from two clean data points (Sprint 2 Wave 1 and Sprint 3 Wave 2 of the lab-tech-portal cleanup engagement).
>
> **Generated:** 2026-05-13 after Sprint 3 Wave 2 PRs (#61, #62) merged and sprint-closed.

---

## Copy-paste prompt for the new session

```
## Design and build the /wave-execute skill — lab-tech-portal

You are picking up after two clean executions of an autonomous wave-orchestration loop. Your job is to abstract that loop into a `/wave-execute` skill, following the patterns established by the existing skills in `.claude/skills/`.

### Why this skill exists

The orchestrator (Opus) has manually run the same outer loop twice:
1. /sprint-kickoff against a plan doc → produces worktrees + per-stream prompts
2. For each stream: spawn a Dev agent (claude subagent_type, model per plan, run_in_background) → wait for it to push and open a PR
3. Once each PR is open: poll for Copilot review (background gh API loop)
4. When Copilot review lands: /review-pr <PR#> --auto (which itself triages, fixes, replies, pushes)
5. Wait for CI green
6. Final summary + next-sprint candidate recommendation

The two data points (Sprint 2 Wave 1 = 3 streams; Sprint 3 Wave 2 = 2 streams) are now both green and merged. The third execution should be a single `/wave-execute --plan <path> --wave N` invocation that runs end-to-end without operator hand-holding, surfacing a tight final report.

### What to read first (in this order)
1. **[docs/skill-development/wave-execute-skill-handoff-2026-05-13.md](./wave-execute-skill-handoff-2026-05-13.md)** — this file. Has the design constraints and the two data points listed below.
2. **[.claude/skills/sprint-kickoff/SKILL.md](../../.claude/skills/sprint-kickoff/SKILL.md)** — the existing skill `/wave-execute` will compose first.
3. **[.claude/skills/review-pr/SKILL.md](../../.claude/skills/review-pr/SKILL.md)** — the existing skill `/wave-execute` will invoke per PR.
4. **[docs/sprint-plans/sprint-2-execution-plan-2026-05-12.md](../sprint-plans/sprint-2-execution-plan-2026-05-12.md)** and **[docs/sprint-plans/sprint-3-execution-plan-2026-05-13.md](../sprint-plans/sprint-3-execution-plan-2026-05-13.md)** — the two waves the skill must support. These are the input contract.
5. **[AGENTS.md](../../AGENTS.md)** — hard rules (JIRA prefix, no direct commits to master, no hooks-skip, etc.).
6. **[docs/workflows/pr-review-tiered.md](../workflows/pr-review-tiered.md)** — canonical review process.

### The two data points (lived experience)

**Wave 1 (Sprint 2):** PRs #58 (Docker), #59 (docs), #60 (Slice A auth). 3 streams in parallel. All Sonnet except #59 (Haiku). Total Copilot comments: 7+6+5 = 18. All round-1 FIX. One CI re-failure on #58 (Dockerfile rm step + .dockerignore tests/ exclusion). One SCOPE acknowledgment on #58 (DATA_DIR — deferred to Sprint 3). Bookkeeping commit (plan status update) folded into first-to-finish stream's PR.

**Wave 2 (Sprint 3):** PRs #61 (Slice B obs), #62 (Slice D-part1). 2 streams in parallel, both Sonnet. Total Copilot comments: 5+3 = 8. All round-1 FIX. No CI re-failures. Bookkeeping commit (Sprint 2 status close-out + new Sprint 3 plan doc) folded into PR #61 (first-to-finish).

### Decisions already made (don't re-litigate)

1. **Auto-fix mode is the default.** Round-1 Copilot comments are auto-fixed across all tiers per [[feedback-guide-friction-workflow]] and Stephen's explicit call in Wave 1. The skill should default to `--auto` behavior. Provide an `--interactive` flag for cases where the operator wants to review the triage table first.
2. **Background agents, not parallel sub-agents.** Use the Agent tool with `run_in_background: true` and `subagent_type: claude` for Dev agents. The orchestrator gets notified when each completes. Do NOT block on agent completion via foreground calls.
3. **Bookkeeping commit pattern:** any uncommitted plan-status updates from the orchestrator get folded into the first stream's branch (NOT a separate PR). The skill should track which stream finishes first and append the bookkeeping commit there before that PR's Copilot review starts.
4. **Two streams or three.** When file overlap forces a deferral (Wave 2 deferred audit log #46 to avoid Slice D-part1 5-tool overlap), the skill should surface the recommendation but let the operator confirm via AskUserQuestion before kickoff. Default recommendation: defer the overlap-prone work.
5. **Line budget overridden.** The 500-line tripwire from the original plan-parallel-streams skill is dead. Default: aim for one PR per stream; only split if >1500 lines mixed concerns. Bake this into the Dev agent prompt template.
6. **Skill abstraction guidance is in [[feedback-autonomous-orchestration]]:** "build from two data points, iterate after Sprint 4 based on observations."

### Key sequencing details (gotchas)

- **Worktree creation must be sequential.** `git worktree add` races on `.git/worktrees/` if parallel. Loop sequentially, not in a foreground multi-tool message.
- **Copilot polls:** background `gh` poll with `until` loop checking `gh pr view --json latestReviews --jq '.latestReviews[] | select(.author.login == "copilot-pull-request-reviewer") | .state'` for COMMENTED/APPROVED/CHANGES_REQUESTED. Sleep 90s between checks.
- **CI poll after each fix push:** same pattern, watching `.statusCheckRollup[] | .conclusion // .status`. Sleep 60s.
- **The Dev agent prompt** lives at `/tmp/sprint-prompts/stream-<X>-wave<N>.md` and is referenced from the Agent prompt via Read. Keep it that way — embedding 5-7KB inline blows context.
- **Reply via `gh api repos/<repo>/pulls/<PR>/comments/<COMMENT_ID>/replies --method POST --field body=...`** — NOT the higher-level `gh pr review`. Multiple replies can run in parallel via `&` + `wait`.
- **PR bookkeeping:** the orchestrator does `git stash push docs/sprint-plans/` before creating worktrees (to keep master clean), then copies the new sprint plan into the first stream's worktree after that agent completes, and commits with `QENG-16846: chore(sprint-N): close-out previous + drop new plan`.

### Action: build the skill

1. Create `.claude/skills/wave-execute/SKILL.md` following the structure of the existing skills (Phase 1 / Phase 2 / etc.).
2. The skill takes `--plan <path> --wave N [--interactive] [--dry-run]`. Defaults to `--auto` review mode.
3. Wire in the orchestration phases:
   - **Phase 0:** Pre-flight (verify base merged, no in-flight conflicting branches, plan parses)
   - **Phase 1:** /sprint-kickoff → worktrees + prompts (compose existing skill)
   - **Phase 2:** Spawn Dev agents in background, one per stream (model per plan)
   - **Phase 3:** On first agent completion, fold any pending bookkeeping commit
   - **Phase 4:** Per-PR: poll Copilot → /review-pr <N> --auto → poll CI → confirm green
   - **Phase 5:** Final summary table + next-sprint candidate recommendation
4. Handle the edge cases the two waves surfaced: CI re-failure (loop back to Phase 4 fix step); SCOPE acknowledgments that don't get auto-fixed (surface in summary); deferred-issue replies (the Refs/Closes distinction from PR #59's #45 handling).
5. Update `.claude/skills/sprint-kickoff/SKILL.md`'s "Next step" section to suggest `/wave-execute` instead of "open VS Code windows and paste prompts."
6. Test against Sprint 3 Wave 3 when it's planned (audit log + tooling follow-ups). That's the third data point.

### Deferred items (do NOT pull into this skill design)

- `/handoff` skill (Slice H follow-up; not yet designed) — referenced in memory but not built.
- Wave 3 / Sprint 4 planning — separate workstream.
- The qe-check install fix upstream PR — different repo (qe-repo-ai-assisted-guide), out of scope here.

### When something goes wrong

- If two-data-points generalization feels forced, flag it. Stephen explicitly said "iterate based on future sprints" — don't over-design.
- The skill should compose existing skills, not duplicate their logic. If you find yourself rewriting /review-pr's triage rules, you're going too deep.
- If the Agent tool's `run_in_background` semantics change between waves and the design relies on them, capture that as a known fragility in the skill doc.
```

---

## Why this handoff file exists

Stephen's preference (2026-05-12): when context-budget is the constraint, write a starter prompt for the next session capturing (a) the lived experience, (b) decisions already made, (c) explicit next steps, (d) gotchas. The original `sprint-2-kickoff-handoff-2026-05-12.md` did this for the Sprint 2 Wave 1 kickoff transition. This file does it for the `/wave-execute` skill-design transition.

The same pattern will eventually generalize into a `/handoff` skill (deferred to Slice H — not yet sketched).

---

## End-of-Wave-2 checklist (done before this file was written)

- [x] PR #61 merged (Slice B observability — /healthz, /readyz, structured JSON logging)
- [x] PR #62 merged (Slice D-part1 — DATA_DIR, db.py extraction, WAL, QR paths, print-request paths)
- [x] `/sprint-close 61` and `/sprint-close 62` executed: 7 issues closed, both worktrees removed, branches cleaned up
- [x] Sprint 3 plan status table marked all merged via the bookkeeping commit in PR #61
- [x] Memory updated: `feedback-autonomous-orchestration` records the "two data points, then abstract" decision
- [x] Master is at `45a999d`, clean tree
