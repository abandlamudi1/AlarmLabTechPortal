---
name: wave-execute
description: End-to-end autonomous wave orchestration. Composes /sprint-kickoff and /review-pr into a single hands-off loop: kickoff → background Dev agents → Copilot poll → /review-pr --auto → CI poll → final report.
argument-hint: "--plan <plan.md> --wave N [--interactive] [--dry-run]"
allowed-tools: Bash(gh *) Bash(git *) Bash(find *) Bash(cat *) Bash(echo *) Bash(mkdir *) Bash(jq *) Bash(npm *) Bash(python *) Bash(grep *) Bash(ls *) Bash(sort *) Bash(sleep *) Bash(./node_modules/.bin/tsc *) Bash(npx *) Read Write Edit Glob Grep Agent AskUserQuestion TodoWrite
---

# Wave Execute: Autonomous Wave Orchestration

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Runs an entire sprint wave end-to-end from a single invocation. Composes `/sprint-kickoff` and `/review-pr`; does not duplicate their logic.

---

## Arguments

Parse `$ARGUMENTS` for:

- **`--plan <path>`** (required): path to the execution plan doc (output of `/plan-parallel-streams`)
- **`--wave N`** (required): wave number to execute
- **`--learnings <path>`** (optional): path to data points file. Default: `docs/wave-execute/data-points.md`
- **`--interactive`**: pause after each `/review-pr` triage table for operator confirmation (default: `--auto`)
- **`--dry-run`**: parse plan, print what would happen, no side effects

---

## Phase 0: Pre-flight

### Step 0.0 — Load prior-wave learnings

Read the last 3 rows of [`docs/wave-execute/data-points.md`](../../docs/wave-execute/data-points.md) and any **Active** entries in [`docs/wave-execute/friction-inventory.md`](../../docs/wave-execute/friction-inventory.md). Surface them as advisory warnings:

```
PRIOR-WAVE LEARNINGS — do not ignore:
- F03 (Active): Dev agents add new imports but leave stale aliases. Watch for this when reviewing Stream A and B's import sections.
- F01 (Mitigated, watch): Stale callers after DB-layer attribute move. Watch if Wave N involves SQLAlchemy / Alembic / model rename.
```

If the previous wave's summary file contains a non-empty **Human Verdict → Carry-forward observations** section, print it verbatim. The orchestrator and downstream agents (sprint-kickoff, Dev agents, review-pr) should treat these as soft constraints for this run.

### Step 0.1 — Parse and validate arguments

Confirm `--plan` file exists and `--wave N` is provided. If either is missing, stop and print usage.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
PLAN_PATH="${PROJECT_ROOT}/<--plan value>"  # resolve relative paths from PROJECT_ROOT
[[ -f "$PLAN_PATH" ]] || { echo "ERROR: plan file not found: $PLAN_PATH"; exit 1; }
```

### Step 0.2 — Verify master is clean and up-to-date

```bash
git fetch origin
LOCAL=$(git rev-parse master)
REMOTE=$(git rev-parse origin/master)
[[ "$LOCAL" == "$REMOTE" ]] || echo "WARNING: local master behind origin — pulling..."
git pull --rebase origin master || { echo "ERROR: git pull --rebase failed — resolve conflicts before continuing"; exit 1; }

# Working tree must be clean (stash is handled in Step 0.5)
git status --porcelain | grep -v '^??' | grep -v '$CONFIG.sprint.plans_dir/' \
  && echo "ERROR: uncommitted changes outside $CONFIG.sprint.plans_dir/ — resolve before running" && exit 1
```

### Step 0.2.5 — Detect stale worktrees from prior sprints

Check for leftover worktrees whose branches are already merged to `origin/master`. These accumulate across sprints and can cause confusion if left unattended.

```bash
# Warn about stale worktrees (branches already merged to master)
git worktree list --porcelain | grep '^branch' | sed 's|branch refs/heads/||' | while read BRANCH; do
  [[ "$BRANCH" == "master" ]] && continue
  if git branch -r --merged origin/master | grep -q "origin/${BRANCH}"; then
    WPATH=$(git worktree list --porcelain | grep -B2 "branch refs/heads/${BRANCH}" | head -1 | sed 's/worktree //')
    echo "WARNING: Worktree for ${BRANCH} is already merged to master. Run: git worktree remove ${WPATH}"
  fi
done
```

If any stale worktrees are found, surface each one with its suggested removal command and recommend running `/branch-cleanup` before proceeding. Clean state (no stale worktrees) proceeds automatically without prompting.

### Step 0.3 — Parse the plan doc

Read the plan file. Extract for Wave N:
- Stream IDs, names, branch names, worktree paths
- Issue numbers per stream
- Model assignment per stream (from the "Agent team allocation" table)
- File footprint per stream (for overlap check)
- Dependency graph (to confirm Wave N-1 is complete)

### Step 0.3.5 — Under-load check

After parsing Wave N's streams, check if the wave is under-loaded:

**Definition of under-loaded:** Fewer than 3 streams in the wave, AND the remaining sprint work after this wave is also thin (e.g., Wave N is the last wave in the sprint and has only 1–2 streams).

**If under-loaded:**

1. Scan all open "Next" milestone issues that are NOT already in the plan:
   ```bash
   gh issue list \
     --repo $CONFIG.repo \
     --milestone "Next" \
     --state open \
     --limit 50 \
     --json number,title,labels \
     | jq '[.[] | select(.number as $n | [<existing_plan_issue_numbers>] | index($n) | not)]'
   ```
2. For each candidate, do a quick file-footprint check (grep for issue-title keywords in the codebase). Exclude any issue that touches files already claimed by Wave N's existing streams.
3. Surface up to 5 compatible candidates with a short rationale:
   ```
   UNDER-LOAD WARNING: Wave N has only {K} streams.
   Candidate additions (no overlap with existing streams):
   - #89: Redis healthcheck in /readyz — touches app.py readyz block only — LOW overlap
   - #90: Celery worker tuning — touches docker-compose.yml + .env.example — LOW overlap
   - #99: Dead code cleanup in tasks — touches tasks/print_request_tasks.py — no Wave N overlap
   Proceed with existing streams, or add candidates?
   ```
4. If the wave is fully autonomous (`--auto` mode) and candidates are identified, add them automatically if their file overlap with existing Wave N streams is LOW. Surface the additions in the Phase 5 summary.
5. For added issues, create worktrees and agent prompts following the same pattern as Phase 1/2 of this skill.

**This check prevents the Sprint 5 Wave 3 failure mode:** where only 1 stream ran when 4 additional compatible issues were available.

### Step 0.4 — Validate Wave N-1 is complete

Check the plan's status tracking table. If any Wave N-1 stream is not marked **merged**, stop:

```
ERROR: Cannot start Wave N — Stream X from Wave N-1 is still {state}.
Merge it first, then run /sprint-close <PR#> to update the plan.
```

### Step 0.5 — File-overlap check

If any two streams share files beyond the expected low-risk additive cases (see the plan's file-overlap matrix), surface them:

```
WARNING: Streams A and B both touch config.py.
Plan classifies this as: LOW (soft edge — additive changes)
Proceed? (y = trust the plan's assessment)
```

Use `AskUserQuestion` only if the plan's overlap matrix flags MEDIUM or HIGH risk, or if a file isn't listed in the matrix at all. For LOW-risk shared files listed in the matrix, proceed automatically.

### Step 0.6 — Stash pending plan-status files

Before any worktrees are created, stash uncommitted plan docs to keep master clean:

```bash
STASH_NEEDED=$(git status --porcelain $CONFIG.sprint.plans_dir/ | grep -c '.' || true)
if [[ "$STASH_NEEDED" -gt 0 ]]; then
  git stash push --include-untracked -- $CONFIG.sprint.plans_dir/
  BOOKKEEPING_STASH=true
  echo "Stashed $CONFIG.sprint.plans_dir/ — will fold into first-to-finish stream's branch"
fi
```

### Step 0.7 — Dry-run exit

If `--dry-run`:
- Print the stream table (ID, branch, issues, model, worktree path)
- Print: "Would spawn N background Dev agents. No side effects."
- Exit.

---

## Phase 1: Kickoff (compose /sprint-kickoff)

Read `.claude/skills/sprint-kickoff/SKILL.md` and execute **Phases 1–3** of that skill for the specified wave, with these adaptations:

1. **Prompt file naming**: Save agent prompts to `/tmp/sprint-prompts/stream-<STREAM_ID>-wave<N>.md` (wave-scoped, not just stream-scoped — avoids collisions across waves).

2. **Skip /sprint-kickoff Phase 4** (VS Code launch commands). Worktrees and prompt files are all that's needed here; agents will be spawned in Phase 2.

3. **Defer /sprint-kickoff Phase 5** (plan status update commit) to Phase 3 of this skill, so the bookkeeping stash can be folded in at the same time.

After Phase 1: all worktrees exist on disk and all prompt files are at `/tmp/sprint-prompts/stream-<ID>-wave<N>.md`.

---

## Phase 2: Spawn Dev agents (background)

Spawn one background Dev agent per stream. Agents run in parallel; do NOT block waiting for them.

For each stream:

```
Agent(
  description: "Stream <ID> Dev agent — Wave <N>: <stream_name>",
  subagent_type: "claude",
  model: "<model_from_plan>",   // "sonnet" or "haiku" per plan's agent allocation table
  run_in_background: true,
  prompt: "Read /tmp/sprint-prompts/stream-<ID>-wave<N>.md and follow the instructions there.
           When your PR is open, report back: PR number and branch name."
)
```

**Model selection:** Use the model specified in the plan's "Agent team allocation" table. Default to `sonnet` if unspecified.

**Line budget in prompt template** (embedded in the sprint-kickoff–generated prompt file, not here):
- Aim for one PR per stream.
- Only split if diff exceeds 1500 lines of genuinely mixed concerns.
- The 600-line tripwire from older plan-parallel-streams output is overridden.

Track a `FIRST_FINISHER` variable (initially unset). The first agent to complete and report a PR number sets this.

---

## Phase 3: Bookkeeping on first-to-finish

When the **first** background agent completes and reports a PR number:

1. Set `FIRST_PR=<reported PR number>` and `FIRST_BRANCH=<reported branch>`.

2. If `BOOKKEEPING_STASH=true` (stash was created in Step 0.6):

   ```bash
   WORKTREE_PATH=<first stream's worktree path>

   # Pop stash into the first stream's worktree
   cd "$WORKTREE_PATH"
   git stash pop
   ```

3. **Update the plan's status table — Wave N streams → in-progress.**

   For each stream in Wave N, use the Edit tool to flip its status row in the plan file:

   ```
   # Before: | A | **ready to kick off** | ... | — | ...
   # After:  | A | **in-progress** | ... | #PR | ...
   ```

   Example — if `$CONFIG.sprint.plans_dir/sprint-6-execution-plan.md` contains:

   ```markdown
   | A | wave-execute SKILL.md fixes | **ready to kick off** | — | #79, #80, #81, #82 |
   ```

   Edit it to:

   ```markdown
   | A | wave-execute SKILL.md fixes | **in-progress** | #<FIRST_PR> | #79, #80, #81, #82 |
   ```

   Then stage the plan file alongside the stash-popped docs:

   ```bash
   git add $CONFIG.sprint.plans_dir/
   git commit -m "$CONFIG.jira.prefix: chore(sprint-N): close Wave N-1 + drop Wave N plan; mark Wave N streams in-progress"

   # Push the additional commit
   git push origin <FIRST_BRANCH>
   ```

   The bookkeeping commit message must note both the close-out **and** the in-progress update so the status transition is auditable.

4. Proceed to Phase 4 for the first PR. Other streams continue running in background.

---

## Phase 4: Per-PR lifecycle

Execute this phase for each stream **as its agent completes** (not all at once). Phases 4 for different streams may interleave.

### Step 4.1 — Get the PR number

The agent reports it on completion. If the agent did not report a PR number, check:

```bash
gh pr list --repo $CONFIG.repo \
  --head <stream_branch> --json number,title,state \
  --jq '.[0].number'
```

### Step 4.1b — Rebase onto master if behind

Before polling for Copilot, check whether the branch has fallen behind `origin/master`
(another stream may have merged while this Dev agent was working). Rebasing here means
Copilot reviews the post-rebase code — not a stale snapshot that gets overwritten later.

```bash
BRANCH=$(gh pr view $PR --repo $CONFIG.repo --json headRefName --jq '.headRefName')
WORKTREE_PATH=$(git worktree list --porcelain \
  | grep -B1 "branch refs/heads/${BRANCH}" | head -1 | sed 's/worktree //')

if [[ -z "$WORKTREE_PATH" ]]; then
  echo "ERROR: cannot find local worktree for branch $BRANCH — skipping rebase check."
  echo "Verify the worktree exists with: git worktree list"
  # Continue to Step 4.2; the conflict will surface at merge time instead.
else
  git -C "$WORKTREE_PATH" fetch origin master

  BEHIND=$(git -C "$WORKTREE_PATH" rev-list HEAD..origin/master --count)

  if [[ "$BEHIND" -gt 0 ]]; then
    echo "Branch $BRANCH is $BEHIND commit(s) behind origin/master — rebasing."
    git -C "$WORKTREE_PATH" rebase origin/master

    if [[ $? -ne 0 ]]; then
      CONFLICTS=$(git -C "$WORKTREE_PATH" diff --name-only --diff-filter=U)
      echo "CONFLICT: rebase of $BRANCH onto origin/master has conflicts:"
      echo "$CONFLICTS"
      echo ""
      echo "Manual resolution required:"
      echo "  cd $WORKTREE_PATH"
      echo "  # resolve conflicts in the files listed above"
      echo "  git add <resolved-files>"
      echo "  git rebase --continue"
      echo "  git push --force-with-lease origin $BRANCH"
      echo ""
      echo "Then resume from Step 4.2 (Copilot poll) for PR #$PR."
      # Mark this stream BLOCKED in Phase 5 summary; continue with other streams.
    else
      git -C "$WORKTREE_PATH" push --force-with-lease origin "$BRANCH"
      echo "Rebase complete — $BRANCH is now up-to-date with master."
    fi
  fi
fi
```

If rebase conflicts: surface the conflicting files, mark the stream as **BLOCKED** in the Phase 5 summary, and continue processing other streams. Do NOT block the whole wave on one stream's conflict.

### Step 4.2 — Poll for Copilot review

Run a background shell poll. Do NOT block the main orchestration thread — use `run_in_background: true` on the Bash call:

```bash
PR=<number>
until gh pr view $PR \
  --repo $CONFIG.repo \
  --json latestReviews \
  --jq '[.latestReviews[] | select(.author.login | startswith("copilot"))] | length > 0' \
  | grep -q true; do
  sleep 90
done
echo "Copilot review ready on PR $PR"
```

While waiting, continue polling other streams' Phase 4 steps if applicable.

### Step 4.3 — Run /review-pr

When Copilot review is confirmed:

```
/review-pr <PR_NUMBER> --auto
```

If `--interactive` was passed to wave-execute, run `/review-pr <PR_NUMBER>` (no `--auto`) and wait for operator confirmation before Phase 4.4.

### Step 4.4 — Poll CI

After /review-pr pushes its fix commit:

```bash
PR=<number>
# Wait for all real checks to complete (pass or fail).
# Use .status (not .conclusion // .status) — conclusion is "" not null when in-progress,
# so the // fallback incorrectly treats in-progress checks as done.
# Filter out phantom null-named checks that appear in some PR statusCheckRollups.
until gh pr view $PR \
  --repo $CONFIG.repo \
  --json statusCheckRollup \
  --jq '[.statusCheckRollup[] | select(.name != null) | .status != "IN_PROGRESS" and .status != "QUEUED" and .status != "PENDING"] | all' \
  | grep -q true; do
  sleep 60
done
```

Then check the result:

```bash
CI_PASS=$(gh pr view $PR \
  --repo $CONFIG.repo \
  --json statusCheckRollup \
  --jq '[.statusCheckRollup[] | select(.name != null) | .conclusion] | map(. == "SUCCESS" or . == "NEUTRAL" or . == "SKIPPED") | all')
```

### Step 4.5 — CI re-failure loop

If `CI_PASS != true`:

1. Read the failing check logs: `gh run view <run_id> --log-failed`
2. Fix the failure in the PR's worktree.
3. Commit: `$CONFIG.jira.prefix: fix(ci): resolve test failure on #<PR>`
4. Push and return to Step 4.4.

Cap at 3 CI fix attempts. On third failure, surface in Phase 5 summary with the error and stop attempting auto-fix.

### Step 4.6 — SCOPE acknowledgment handling

SCOPE items from `/review-pr` are acknowledged but not auto-fixed. They create GitHub issues via `/create-issue`. Collect the issue numbers for the Phase 5 summary. Do NOT treat a SCOPE item as a blocker — proceed to CI green and merge readiness regardless.

---

## Phase 5: Final summary

When all streams have CI-green PRs (or have been surfaced as blocked), produce **three artifacts**:

### Step 5.1 — Write the persistent wave summary file

Copy [`docs/wave-execute/TEMPLATE-wave-summary.md`](../../docs/wave-execute/TEMPLATE-wave-summary.md) to:

```
docs/wave-execute/sprint-<N>-wave-<M>-<YYYY-MM-DD>.md
```

Fill in:
- **Outcomes** table (stream / PR / branch / Copilot rounds / CI re-fixes / time-to-merge / status)
- **Friction encountered** — every item that triggered a non-standard action (CI re-fix, dead-import discovery, scope expansion). For each, link to [[friction-inventory.md]] if recurring, or mark `new` if first observation.
- **Patterns observed** — review-classification distribution, common failure modes, time-to-merge insights
- **Recommended next actions** — proposed issues for next-sprint groom as `- [ ]` checkboxes. The human ticks the boxes during review; ticked items become issues.
- **Data-points entry** — the one-line row to append to `data-points.md`
- Leave the **Human Verdict** section blank — the human fills it in during review.

This file is the **canonical record** of the wave. It subsumes daily changelogs for the wave duration.

### Step 5.2 — Append to data-points.md

Append the one-line row (from the summary file's "Data-points entry" section) to the table in [`docs/wave-execute/data-points.md`](../../docs/wave-execute/data-points.md). Never edit historical rows.

### Step 5.3 — Auto-create issues per the threshold rule

Read [`docs/wave-execute/friction-inventory.md`](../../docs/wave-execute/friction-inventory.md) status legend. Apply the threshold rules:

- **First-time friction**: do NOT auto-create. Surface in the wave summary's "Recommended next actions" as a `- [ ]` checkbox. Human ticks the box during review.
- **Second-time friction** (recurring): auto-create issue with label `wave-friction` and milestone "next sprint". Still listed in the summary for human visibility.
- **Third-time friction**: block before next wave — print a `BLOCKING` warning in this Phase 5 output. The next `/wave-execute` Phase 0 will refuse to start until the friction-inventory entry is upgraded to Mitigated or Closed.

### Step 5.4 — Print operator-facing summary

Echo this short summary to the chat so the operator sees it immediately:

```
## Wave <N> Summary — see docs/wave-execute/sprint-<N>-wave-<M>-<YYYY-MM-DD>.md

| Stream | PR  | CI | Status |
|--------|-----|----|--------|
| A      | #NN | ✓  | ready  |
| B      | #NN | ✓  | ready  |

Auto-created issues (recurring friction): <count>, e.g. #NNN
Proposed issues awaiting human tick: <count>

After all merges: run `/sprint-close --batch <PR1>,<PR2>,... --plan <plan_file>`
```

Build the `--batch` argument by collecting every PR number reported by the wave's streams:

```bash
# Example — substitute actual PR numbers from STREAM_PRS array:
BATCH_PRS=$(IFS=','; echo "${STREAM_PRS[*]}")
echo "After all merges: run /sprint-close --batch ${BATCH_PRS} --plan ${PLAN_PATH}"
```

---

## Edge Cases

### Agent fails to open a PR

If a background agent completes but does not report a PR number and none exists on the branch:

1. Check the agent's output for error details.
2. Surface in summary: "Stream X did not produce a PR. Manual intervention needed."
3. Continue with other streams.

### Bookkeeping stash conflicts with agent work

If `git stash pop` in Phase 3 produces a conflict (unlikely — stash is docs-only, agents touch code):

1. Resolve conflict manually in the worktree.
2. Complete the commit and push as normal.
3. Surface as a note in Phase 5 summary.

### Multiple Copilot review rounds

If `/review-pr --auto` on round 1 pushes fixes and Copilot re-reviews, the CI poll (Step 4.4) will catch the new push. Re-run `/review-pr <N> --auto --round 2` if unresolved comments remain after CI green. Cap at round 3; then chain `/defer-pr-comments <N> --auto` per the review-pr skill's round-3+ logic.

### Refs vs Closes in PR bodies

When a stream's PR references an issue that is not fully resolved in that PR (e.g., partial implementation, or issue deferred to a future wave), use `Refs #N` not `Closes #N` in the PR body. The Dev agent prompt template (generated by /sprint-kickoff) should specify which issues get `Closes` vs `Refs`.

---

## Known Fragilities

**Recurring friction lives in [`docs/wave-execute/friction-inventory.md`](../../docs/wave-execute/friction-inventory.md)** and is surfaced automatically in Phase 0.0. The list below is for mechanism-level dependencies that won't be addressed by a per-wave rule:

- **`run_in_background` semantics**: This skill relies on the Agent tool's `run_in_background: true` parameter and the resulting completion notification. If this behavior changes between Claude Code versions, the Phase 2 spawn pattern may need adjustment. Treat as a known dependency.
- **Copilot poll**: The `startswith("copilot")` login filter matches `copilot-pull-request-reviewer` and the `[bot]` variant. If GitHub renames the bot, the poll will spin indefinitely — cap at 20 iterations (30 min) before alerting.
- **CI poll: `conclusion` is `""` not `null` when in progress.** GitHub's `statusCheckRollup` sets `conclusion` to empty string (not null) while a check runs. `.conclusion // .status` short-circuits on the empty string and reports the check as done prematurely. Step 4.4's corrected poll uses `.status` directly and filters phantom null-named checks with `select(.name != null)`. Do not revert.
- **Iteration policy**: don't over-engineer for hypothetical N-stream cases. Each wave appends to `data-points.md`; review the timeline of real waves before adding new orchestration features.

---

## Related Docs

**Data files this skill reads/writes:**
- `docs/wave-execute/data-points.md` — append-only timeline (Phase 5 appends, Phase 0.0 reads last 3 rows)
- `docs/wave-execute/friction-inventory.md` — recurring friction patterns (Phase 0.0 surfaces Active entries)
- `docs/wave-execute/TEMPLATE-wave-summary.md` — copied at Phase 5.1 to produce per-wave summary
- `docs/wave-execute/sprint-<N>-wave-<M>-<date>.md` — per-wave summaries (canonical record)

**Skills this skill composes or hands off to:**
- `.claude/skills/sprint-kickoff/SKILL.md` — Phase 1 composition target
- `.claude/skills/review-pr/SKILL.md` — Phase 4 composition target
- `.claude/skills/plan-parallel-streams/SKILL.md` — produces the plan this skill consumes
- `.claude/skills/sprint-close/SKILL.md` — post-merge lifecycle (run after each merge)

**Reference docs:**
- `docs/workflows/pr-review-tiered.md` — canonical review classification rules
- `AGENTS.md` — hard rules (JIRA prefix, no direct master commits, no hooks-skip)

---

## On Complete

1. Confirm the persistent wave summary file exists at `docs/wave-execute/sprint-<N>-wave-<M>-<date>.md`.
2. Confirm `docs/wave-execute/data-points.md` has the new row appended.
3. Print the short operator-facing summary from Step 5.4.
4. Pass each PR number forward to `/sprint-close <PR#>` after merge.
5. Remind the operator to fill in the Human Verdict section of the summary file before the next `/wave-execute` runs.
