---
name: sprint-kickoff
description: Create worktrees, generate agent prompts, and launch a wave of parallel Dev agents from an execution plan. Bridges the gap between /plan-parallel-streams output and agent execution.
argument-hint: "--plan <plan.md> [--wave N] [--dry-run] [--streams A,B,C]"
allowed-tools: Bash(gh *) Bash(git *) Bash(code *) Bash(find *) Bash(cat *) Bash(echo *) Bash(mkdir *) Bash(jq *) Bash(npm *) Bash(grep *) Bash(ls *) Bash(sort *) Read Write Glob Grep TodoWrite
---

# Sprint Kickoff: Worktree Creation + Agent Launch Orchestration

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Given an execution plan document (produced by `/plan-parallel-streams`), create worktrees for a specific wave and generate everything needed to launch Dev agents.

---

## Why This Skill Exists

**Problem**: After `/plan-parallel-streams` produces a plan, the operator must manually:
1. Run `git worktree add` for each stream (6× for a typical wave)
2. Open a VS Code window in each worktree
3. Copy-paste a tailored agent prompt into each window
4. Update the plan status table

This takes 15–20 minutes and is error-prone. Parallel `git worktree add` from multiple agents races on `.git/worktrees/`, so it must be sequential.

**Solution**: This skill automates the full kickoff sequence from a plan document.

---

## Repository & Project Constants

```
REPO          = $CONFIG.repo
```

Derive paths at runtime rather than hardcoding them:

```bash
# Determine project root from the git repo itself (works on any machine)
PROJECT_ROOT=$(git rev-parse --show-toplevel)
# Worktrees live as siblings of the project root directory
WORKTREE_ROOT=$(dirname "$PROJECT_ROOT")
```

---

## Invocation Modes

### Mode 1: Full kickoff (default)
```
/sprint-kickoff --plan $CONFIG.sprint.plans_dir/now-milestone-execution-plan-2026-04-17.md --wave 1
```
Parse the plan, create all Wave 1 worktrees, generate agent prompts, and print launch commands.

### Mode 2: Specific streams
```
/sprint-kickoff --plan $CONFIG.sprint.plans_dir/X.md --wave 1 --streams A,B,C
```
Kickoff only specific streams from a wave (useful for partial restarts).

### Mode 3: Dry run
```
/sprint-kickoff --plan $CONFIG.sprint.plans_dir/X.md --wave 1 --dry-run
```
Print what would be done without creating worktrees or modifying the plan.

---

## Phase 1: Parse the Execution Plan

### Step 1.1 — Read the plan document

Read the plan markdown file. Extract:
- **Wave N streams**: From the "Worktree design" table for the specified wave
- **Per stream**: worktree path, branch name, issue numbers, SP, touched paths
- **Conflict-cutting rules**: The rules section (to embed in agent prompts)
- **Agent allocation**: Model assignments per stream
- **Dependency graph**: Which streams block which

### Step 1.2 — Validate prerequisites

```bash
# Ensure main is up to date
git checkout main
git fetch origin
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/master)
if [[ "$LOCAL" != "$REMOTE" ]]; then
  echo "WARNING: main is behind origin/master. Running git pull --rebase..."
  git pull --rebase origin main
fi

# Check for existing worktrees that might conflict
git worktree list | grep -v "$(pwd)"
```

If any listed worktree matches a stream name from the plan, warn: "Worktree already exists for stream X. Skip or remove?"

### Step 1.3 — Verify Wave dependencies

If `--wave N` where N > 1:
1. Read the plan's status tracking table
2. Confirm all Wave N-1 streams are marked "merged"
3. If any Wave N-1 stream is not merged, **STOP** and report: "Cannot start Wave N — Stream X from Wave N-1 is still {state}. Merge it first."

---

## Phase 2: Create Worktrees

### Step 2.1 — Sequential worktree creation

Create worktrees ONE AT A TIME (never parallel — races on `.git/worktrees/`):

```bash
for stream in "${STREAMS[@]}"; do
  WORKTREE_PATH="${WORKTREE_ROOT}/${stream.worktree_name}"
  BRANCH_NAME="${stream.branch_name}"

  echo "Creating worktree for Stream ${stream.id}: ${WORKTREE_PATH}"

  # Create branch from current main
  git worktree add "${WORKTREE_PATH}" -b "${BRANCH_NAME}" origin/master

  # Verify
  if [[ -d "${WORKTREE_PATH}" ]]; then
    echo "  ✓ Worktree created: ${WORKTREE_PATH}"
    echo "  ✓ Branch: ${BRANCH_NAME}"
  else
    echo "  ✗ FAILED to create worktree for Stream ${stream.id}"
    exit 1
  fi
done
```

### Step 2.2 — Install dependencies in each worktree (if needed)

For streams that touch frontend code:
```bash
if echo "${stream.touched_paths}" | grep -q "frontend/"; then
  echo "  Installing frontend deps in ${WORKTREE_PATH}..."
  cd "${WORKTREE_PATH}/frontend" && npm ci --silent && cd -
fi
```

For streams that touch backend code:
```bash
if echo "${stream.touched_paths}" | grep -q "backend/"; then
  echo "  Backend: using shared .venv (symlinked from main repo)"
fi
```

---

## Phase 3: Generate Agent Prompts

### Step 3.1 — Fetch issue bodies

For each stream, fetch the full issue body for every issue in that stream:

```bash
for issue_num in "${stream.issues[@]}"; do
  gh issue view "${issue_num}" \
    --repo $CONFIG.repo \
    --json number,title,body \
    | jq '.'
done
```

### Step 3.2 — Build the agent prompt

For each stream, generate a self-contained prompt that includes everything the Dev agent needs. Use this template:

```markdown
# Sprint Stream {STREAM_ID}: {STREAM_NAME}

## Your Assignment

You are a Dev agent working on Stream {STREAM_ID} of the {MILESTONE} milestone sprint.
Your worktree: `{WORKTREE_PATH}`
Your branch: `{BRANCH_NAME}`

## Issues to Implement

{FOR EACH ISSUE IN STREAM:}
### Issue #{NUMBER}: {TITLE}

{ISSUE_BODY}

---
{END FOR}

## Implementation Order

{DEPENDENCY_ORDER within stream — models first, then APIs, then frontend, then tests}

## Constraints

1. **Line budget**: Your PR diff MUST NOT exceed 600 lines (additions + deletions). If approaching this limit, split into multiple PRs on the same branch. Each sub-PR must be independently CI-green.
2. **Branch**: Work exclusively on `{BRANCH_NAME}`. Do not touch other branches.
3. **Rebase before pushing**: `git fetch origin && git rebase origin/master`
4. **PR title format**: `$CONFIG.jira.prefix: {conventional_commit_scope}: {description}`
5. **One concern per PR**: If the stream has multiple issues, you may combine them in one PR only if total diff < 600 lines.
6. **No throwaway scripts**: Use `.scripts/` for any temporary tooling, clean up after.
7. **Tests**: Include unit tests for any new backend logic. Frontend components need basic render tests.

## Conflict-Cutting Rules

{PLAN_CONFLICT_RULES}

## When Done

1. Push your branch: `git push -u origin {BRANCH_NAME}`
2. Create a PR: `gh pr create --title "$CONFIG.jira.prefix: {scope}: {description}" --body "Closes #{ISSUES}"`
3. Report the PR number — the operator will run `/review-pr {PR#}` after Copilot reviews it.
```

### Step 3.3 — Save prompts to disk

Save each agent prompt to a temporary location for easy copy-paste:

```bash
mkdir -p /tmp/sprint-prompts
echo "${PROMPT}" > "/tmp/sprint-prompts/stream-${STREAM_ID}.md"
```

---

## Phase 4: Launch Commands

### Step 4.1 — Print VS Code launch commands

For each stream, print the command to open its worktree in a new VS Code window:

```bash
echo "=== Launch Commands ==="
for stream in "${STREAMS[@]}"; do
  echo ""
  echo "# Stream ${stream.id}: ${stream.name}"
  echo "code ${stream.worktree_path}"
  echo "# Then paste the prompt from: /tmp/sprint-prompts/stream-${stream.id}.md"
done
```

### Step 4.2 — Print the monitoring dashboard

```markdown
## Wave {N} Monitoring

| Stream | Worktree | Agent | Status | PR |
|--------|----------|-------|--------|----|
| A | ../FW-eval-now-A-admin | Dev (Haiku) | Launched | — |
| B | ../FW-eval-now-B-discovery | Dev (Sonnet) | Launched | — |
| ... | ... | ... | ... | ... |

### Quick checks:
- Worktree health: `git worktree list`
- All branches: `git branch -r | grep feat/now`
- Open PRs: `gh pr list --state open --label "sprint"`
```

---

## Phase 5: Update Plan Status

### Step 5.1 — Update the status tracking table

In the plan document, find the status tracking table and update each stream's state:

```markdown
| Sprint | Issues | State | Branch | PR | Depends on |
|--------|--------|-------|--------|----|------------|
| A | #598, #597 | **in-progress** | feat/now-A-admin-polish | — | — |
| B | #596 | **in-progress** | feat/now-B-discovery-pagination | — | — |
```

### Step 5.2 — Commit the plan update

```bash
cd "${PROJECT_ROOT}"
git add $CONFIG.sprint.plans_dir/
git commit -m "docs: update plan status — Wave ${WAVE} kicked off"
```

---

## Error Recovery

### Worktree creation fails
If `git worktree add` fails (e.g., branch already exists):
```bash
# If branch exists but no worktree
git branch -D "${BRANCH_NAME}" 2>/dev/null
git worktree add "${WORKTREE_PATH}" -b "${BRANCH_NAME}" origin/master
```

### Worktree already exists
If the worktree path already exists on disk:
1. Check if it's from a previous sprint: `git -C "${WORKTREE_PATH}" log --oneline -1`
2. If it has unmerged changes, **STOP** and ask the operator
3. If it's stale (merged or abandoned): `git worktree remove "${WORKTREE_PATH}" --force`

### Dependency gate not met
If Wave N-1 streams aren't all merged, print a specific status:
```
Wave 1 status:
  ✓ Stream A — merged (PR #630)
  ✓ Stream B — merged (PR #631)
  ✗ Stream G — open (PR #633, awaiting CI)
  
Cannot start Wave 2. Stream F depends on Stream G.
Run /sprint-close 633 after merge, then retry /sprint-kickoff --wave 2.
```

---

## Related Docs

- `docs/workflows/sprint-skill-chain.md` — full workflow chain
- `docs/workflows/multi-agent-worktree-workflow.md` — worktree mechanics
- `.claude/skills/plan-parallel-streams/SKILL.md` — produces the plan this skill consumes
- `.claude/skills/review-pr/SKILL.md` — next skill after agents produce PRs
- `.claude/skills/sprint-close/SKILL.md` — post-merge lifecycle

---

## On Complete

When all worktrees are created and agent prompts are generated:

1. **Tell the user**: "Wave {N} kicked off. {M} worktrees created. Agent prompts saved to `/tmp/sprint-prompts/`."
2. **Print launch commands**: The VS Code `code <path>` commands for each worktree.
3. **Suggest next action**: Run `/wave-execute --plan <plan.md> --wave N` to spawn Dev agents, poll for Copilot review, run `/review-pr --auto` per PR, and get a final summary — all in one invocation. Alternatively, launch each VS Code window manually and paste the corresponding prompt, then run `/review-pr <PR#>` per PR.
4. **Pass forward**: The PR numbers (once created by agents) are the input to `/review-pr` or the `--plan` + `--wave` flags are the input to `/wave-execute`.
