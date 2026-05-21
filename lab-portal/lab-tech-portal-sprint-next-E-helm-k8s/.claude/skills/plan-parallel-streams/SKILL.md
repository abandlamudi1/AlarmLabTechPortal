---
name: plan-parallel-streams
description: Analyze a milestone's issues, discover file footprints via sub-agents, compute overlap, and produce a parallelized execution plan with non-overlapping worktree streams. Prevents merge-conflict debt while maximizing agent throughput.
argument-hint: "[--milestone <name> | --issues <N,N,...>] [--dry-run] [--wave <N>]"
allowed-tools: Bash(gh *) Bash(git *) Bash(find *) Bash(python *) Bash(jq *) Bash(sort *) Bash(comm *) Bash(grep *) Bash(ls *) Bash(cat *) Bash(echo *) Bash(wc *) Read Write Glob Grep Agent TodoWrite
---

# Plan Parallel Streams: Milestone → Non-Overlapping Worktree Execution Plan

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Given a milestone (or issue list), produce a parallel execution plan that groups issues into independent worktree streams with zero file overlap between them. Uses sub-agents to discover hidden scope that isn't explicit in ticket descriptions.

---

## Why This Skill Exists

**Problem**: Worktree-per-issue causes compound rebase conflicts, duplicate Copilot reviews, and migration collisions when issues share files. Serializing everything wastes 70-80% of agent capacity.

**Solution**: Automatically detect file-level overlap between issues, cluster into non-overlapping streams, and produce a wave-based execution plan where each stream can be a parallel worktree with zero merge-conflict risk between streams.

**Key insight from lessons learned** (`docs/workflows/worktree-lessons-learned.md`): Group by concern area, not per issue. Serialize only where files actually collide. This skill automates that analysis.

---

## Repository & Project Constants

```
REPO          = $CONFIG.repo
PROJECT_NUMBER = $CONFIG.github.project_number
MILESTONES    = Now, Next, Later, Icebox
```

---

## Invocation Modes

### Mode 1: Milestone scan (default)
```
/plan-parallel-streams --milestone Now
```
Analyze all open issues in the given milestone and produce a full parallelized plan.

### Mode 2: Specific issues
```
/plan-parallel-streams --issues 539,541,589,596,597,598
```
Analyze a specific set of issues (useful for partial milestone planning or ad-hoc grouping).

### Mode 3: Dry run (overlap report only)
```
/plan-parallel-streams --milestone Now --dry-run
```
Produce the overlap matrix and stream groupings but skip agent allocation and execution plan output. Good for quick reconnaissance.

### Mode 4: Wave N only
```
/plan-parallel-streams --milestone Now --wave 2
```
Plan the next wave, assuming prior waves have merged. Re-scans `master` for current state.

---

## Phase 0: Pre-flight AC Verification

**Why this phase exists**: In the 2026-04-20 Wave 1 sprint, 2 of 6 agents worked on issues whose ACs were already shipped by prior PRs (#599, #590). Sprint A produced an 8-line docstring-only PR. This phase catches that before agents are spawned.

### Step 0.1 — For each issue, verify ACs against `origin/master`

For every issue in the manifest:

1. Extract the **acceptance criteria** (checkbox items from the issue body)
2. Extract the **"Files to Modify"** list from the issue body
3. For each AC, identify the key symbol/string it introduces (e.g., `helperText` prop, `has_more` field, `anchor="bottom end"`)
4. Grep `origin/master` for those symbols:

```bash
git fetch origin
for symbol in "helperText" "has_more" "anchor=\"bottom end\""; do
  echo "--- Checking: $symbol ---"
  git grep -n "$symbol" origin/master -- $(echo "$FILES_TO_MODIFY" | tr ',' ' ')
done
```

### Step 0.2 — Classify each issue

| Classification | Criteria | Action |
|---|---|---|
| **Shipped** | ≥80% of AC symbols already present in listed files | Close issue with comment: "ACs already satisfied by PR #NNN. Verified by pre-flight check." |
| **Partial** | 20–80% of AC symbols present | Revise scope: list only the unmet ACs. Update the GitHub issue body. Keep in plan with reduced SP. |
| **Open** | <20% of AC symbols present | No change — proceed to Phase 1. |

### Step 0.3 — Update the issue manifest

Remove **Shipped** issues from the manifest. For **Partial** issues, annotate the manifest with the gap-only scope. Report:

```markdown
### Pre-flight AC Verification Results

| Issue | Title | Status | Evidence | Action |
|-------|-------|--------|----------|--------|
| #597  | Admin polish: helper text | Shipped | `helperText` found in VideoQeInlineEditTable.tsx | Close — shipped in PR #599 |
| #596  | Team discovery pagination | Partial | `has_more` present, but Load More button missing | Descope to frontend-only |
| #589  | Teams discovery hardening | Open | 0/5 AC symbols found | Proceed |
```

**STOP if all issues are Shipped**: Report that the milestone is already satisfied and suggest running `/backlog-groom --apply` to close remaining issues.

---

## Phase 1: Issue Discovery & Enrichment

### Step 1.1 — Fetch all open milestone issues (do not pre-filter by slice label)

Fetch every open issue for the target milestone. **Never pre-filter by slice label or category before running the overlap analysis** — the overlap matrix determines grouping, not the ticket's label. Pre-filtering leaves parallelizable work idle and produces under-loaded sprints.

```bash
gh issue list \
  --repo $CONFIG.repo \
  --milestone "<milestone>" \
  --state open \
  --limit 100 \
  --json number,title,body,labels,assignees \
  | jq '.'
```

Store the result as the **issue manifest**.

### Step 1.1.5 — Sprint capacity check and backlog augmentation

After fetching the milestone issues, check whether the issue count is likely to produce an under-loaded sprint:

**Target capacity:** 20–30 story points per sprint, with a minimum of 8 parallel streams across all waves combined. If the milestone scan returns fewer than 8 issues, the sprint is likely under-loaded.

**If fewer than 8 issues found in the milestone:**

1. Check for additional open issues with no milestone (unassigned backlog):
   ```bash
   gh issue list \
     --repo $CONFIG.repo \
     --state open \
     --limit 50 \
     --json number,title,body,labels,milestone \
     --jq '[.[] | select(.milestone == null)]'
   ```
2. Check the next most-ready milestone (e.g., if planning "Next", also pull "Later" issues that have no blocking dependencies):
   ```bash
   gh issue list \
     --repo $CONFIG.repo \
     --milestone "Later" \
     --state open \
     --limit 50 \
     --json number,title,body,labels \
     | jq '.'
   ```
3. From these additional issues, identify candidates that are:
   - Self-contained (no dependency on unshipped issues)
   - Do not reference future slices that depend on the current sprint's work
   - Labeled `could have`, `enhancement`, or `chore`
4. **Surface candidates** to the operator: print a list of 3–5 recommended additions with rationale. The operator decides whether to include them before Phase 2 runs.
5. If the operator adds any, re-run Step 1.1 with the augmented list before proceeding to Step 1.2.

**Capacity framing in the plan output:** Always include an explicit "Sprint capacity" line in the plan header:
```markdown
**Sprint capacity target:** 20–30 story points | Target waves: 2–3 | Target streams/wave: 5–8
**Actual scoped:** N issues, estimated M story points
**Shortfall:** If M < 15, flag as under-loaded and list the candidate additions above.
```

### Step 1.2 — File footprint discovery (sub-agent per issue)

For each issue, dispatch a **search sub-agent** (or do sequentially if <6 issues) to produce a **file footprint**: the set of files that issue will likely touch.

**Sub-agent prompt template:**

> You are analyzing GitHub issue #NNN for the lab-tech-portal repo.
>
> **Issue title**: {title}
> **Issue body**: {body}
>
> Your job: Identify EVERY file in the workspace that this issue will likely create or modify.
>
> Methodology:
> 1. Read the issue body carefully. Extract mentioned files, endpoints, components, schemas, models.
> 2. For each mentioned entity, search the codebase for its current location.
> 3. Check for IMPLICIT scope not mentioned in the ticket:
>    - If a backend API route changes, check the corresponding frontend API client (`frontend/src/api/`)
>    - If a model changes, check for Alembic migrations needed (`backend/migrations/`)
>    - If a schema changes, check API routes that import it, and frontend types that mirror it
>    - If a service changes, check Celery tasks that call it (`backend/tasks/`)
>    - If a frontend component changes, check its parent page and any shared hooks
>    - If config changes, check `backend/config.py` and `docker-compose.yml`
>    - If test infrastructure changes, check `conftest.py`, CI workflow files (`.github/workflows/`)
> 4. For each file, classify the change type: CREATE, MODIFY, or HEAVY_MODIFY (>50 lines)
>
> Return a JSON object:
> ```json
> {
>   "issue": NNN,
>   "files": [
>     {"path": "backend/api/admin.py", "change": "MODIFY", "reason": "add pagination params"},
>     {"path": "backend/schemas/auth.py", "change": "MODIFY", "reason": "new page/size fields"}
>   ],
>   "implicit_scope": [
>     "Issue mentions pagination but doesn't mention frontend/src/api/admin.ts which calls this endpoint"
>   ],
>   "migrations_needed": true|false,
>   "config_changes": true|false
> }
> ```

**Codebase zones to check for implicit scope:**

| If ticket mentions... | Also check these paths |
|---|---|
| Backend API route (`backend/api/*.py`) | `backend/schemas/`, `frontend/src/api/`, `backend/tests/api/` |
| Database model (`backend/models/*.py`) | `backend/migrations/versions/`, `backend/schemas/` |
| Service (`backend/services/*.py`) | `backend/tasks/`, `backend/api/` (callers), `backend/tests/services/` |
| Frontend component (`frontend/src/components/`) | Parent page in `frontend/src/pages/`, shared hooks, `frontend/src/tests/` |
| Config (`backend/config.py`) | `docker-compose.yml`, `.env.example`, deployment manifests |
| CI/CD (`.github/workflows/`) | `Dockerfile`, `.node-version`, `.python-version` |
| Celery task (`backend/tasks/`) | `backend/tasks/celery_app.py`, `backend/services/` (called services) |

### Step 1.3 — Migration conflict pre-check

```bash
# Current highest migration in main
ls backend/migrations/versions/ | sort | tail -1

# Check any in-flight branches with migrations
for branch in $(git branch -r --list 'origin/feat/*' 'origin/fix/*' 'origin/chore/*'); do
  MIGRATIONS=$(git diff main...$branch --name-only | grep 'migrations/versions/' || true)
  if [[ -n "$MIGRATIONS" ]]; then
    echo "Branch $branch has migration: $MIGRATIONS"
  fi
done
```

Record the next available migration number. If multiple streams need migrations, assign numbers sequentially (stream A gets N+1, stream B gets N+2, etc.) and document this in the plan.

---

## Phase 2: Overlap Analysis

### Step 2.1 — Build the overlap matrix

For each pair of issues (i, j), compute:

```
overlap(i, j) = |files(i) ∩ files(j)| / min(|files(i)|, |files(j)|)
```

Using the Jaccard-like ratio against the smaller set prevents a 1-file issue from always showing low overlap against a 20-file issue.

Present as a matrix:

```markdown
### File Overlap Matrix (% of smaller footprint)

|       | #539 | #541 | #589 | #596 | #597 | #598 |
|-------|------|------|------|------|------|------|
| #539  |  —   |  0%  |  0%  | 10%  |  0%  |  0%  |
| #541  |      |  —   |  0%  |  0%  |  0%  |  0%  |
| #589  |      |      |  —   |  0%  |  0%  |  0%  |
| #596  |      |      |      |  —   | 20%  | 15%  |
| #597  |      |      |      |      |  —   | 60%  |
| #598  |      |      |      |      |      |  —   |
```

### Step 2.2 — Identify shared files

List every file that appears in 2+ issue footprints:

```markdown
### Shared Files

| File | Issues | Risk |
|------|--------|------|
| `backend/config.py` | #589, #541 | LOW — additive env vars, unlikely conflict |
| `frontend/src/components/admin/UserManagementSection.tsx` | #597, #598 | HIGH — both modify render logic |
```

Classify risk:
- **LOW**: Both issues add non-overlapping content (e.g., new env vars to config)
- **MEDIUM**: Both issues modify different functions in the same file
- **HIGH**: Both issues modify the same function/component/section

### Step 2.3 — Cluster into streams

Apply **connected components** grouping:
1. Create an edge between issues i and j if `overlap(i, j) > 30%` OR any shared file has HIGH risk
2. Find connected components — each component becomes a **stream**
3. Issues with no edges become singleton streams (fully independent)

**Escape hatch**: If an edge exists only because of a shared LOW-risk file (e.g., both add a line to `config.py`), the operator can override and split them. Flag these as "soft edges" in the output.

---

## Phase 3: Stream Formation & Wave Planning

### Step 3.1 — Form streams

For each cluster from Phase 2, create a stream:

```markdown
### Stream A: Admin UI Polish
- **Issues**: #597, #598
- **Why grouped**: 60% file overlap on `UserManagementSection.tsx`
- **Total SP**: 2
- **Worktree**: `../lab-tech-portal-now-A-admin-polish`
- **Branch**: `feat/now-A-admin-polish`
- **File footprint**: [list unique files across all issues in stream]
```

Within each stream, order issues by dependency:
1. Schema/model changes first
2. API route changes second
3. Frontend changes third
4. Tests last

### Step 3.2 — Dependency analysis between streams

Check for **cross-stream dependencies**:
- Does stream B's API depend on a migration in stream A?
- Does stream F's CI change conflict with stream G's Dockerfile change?
- Does stream H's config change affect stream B's service?

Build a dependency DAG:

```
Stream A ──┐
Stream B ──┤
Stream C ──┼──► can all run in parallel (Wave 1)
Stream D ──┤
Stream G ──┼──► blocks Stream F
Stream H ──┘

Stream E ──┐
Stream F ──┴──► Wave 2 (after dependencies merge)
```

### Step 3.3 — Assign waves

- **Wave 1**: All streams with no incoming dependencies
- **Wave 2**: Streams that depend on Wave 1 merges
- **Wave N**: Continue until all streams are assigned

**Rule**: A stream in Wave N cannot start until ALL its dependency streams from Wave N-1 have merged to `master`.

### Step 3.4 — Cross-stream integration risks

Dispatch a **critic sub-agent** to review the proposed streams for hidden coupling:

> You are reviewing a proposed parallel execution plan for the lab-tech-portal repo.
>
> **Streams**: [stream definitions with file footprints]
>
> Check for:
> 1. **Import chain coupling**: Does stream A modify a module that stream B imports? (Search for `from backend.services.X import` across both footprints)
> 2. **Shared test fixtures**: Do both streams need to modify `conftest.py` or test factories?
> 3. **Runtime coupling**: Do both streams modify services that interact at runtime (e.g., WebSocket manager + auth service)?
> 4. **Config coupling**: Do both streams add env vars that interact (e.g., both add Redis config)?
> 5. **Frontend shared state**: Do both streams modify Zustand stores or React Query keys that could collide?
>
> For each risk found, recommend: MERGE_STREAMS, ADD_DEPENDENCY_EDGE, or ACCEPTABLE_RISK (with mitigation).

---

## Phase 4: Agent Team Allocation

### Step 4.1 — Classify each stream

| Classification | Criteria | Dev Model | QE Model |
|---|---|---|---|
| **Trivial** | SP ≤ 2, single concern, CSS/config only | Haiku | Haiku |
| **Standard** | SP 3-5, existing patterns, well-defined scope | Sonnet | Haiku |
| **Complex** | SP 5-8, new patterns, multi-system, or novel architecture | Sonnet (consider Opus) | Sonnet |
| **Architectural** | SP 8+, new subsystem, cross-cutting concerns | Opus | Sonnet |

### Step 4.2 — Assign agents per stream

Follow `docs/AGENT-MODEL-SELECTION.md` for model tiers. Each stream gets:
- **1 Dev agent** (model based on classification)
- **1 QE agent** (model based on classification, runs parallel to Dev on test files)
- **Shared Architect** (Opus, one-shot overlap recheck at Wave kickoff)
- **Shared Critic** (Haiku, pre-PR gate for each stream)

### Step 4.3 — Line-budget enforcement

Every agent prompt MUST include this constraint:

> **Line budget**: Your PR diff MUST NOT exceed 600 lines (additions + deletions). If your changes approach this limit:
> 1. STOP before committing
> 2. Split your work into logical sub-PRs (e.g., backend-only + frontend-only, or model+schema + API+tests)
> 3. Create the first PR, note remaining work, then continue with a second commit/PR on the same branch
> 4. Each sub-PR must be independently reviewable and CI-green
>
> Exceeding 600 lines without splitting is a blocking review finding.

Record the line budget in the plan document under "Conflict-cutting rules" and in each agent's prompt template.

If a stream's estimated scope exceeds 600 lines (based on SP > 5 or > 8 files), pre-plan the split in the stream definition:

```markdown
### Stream H: Teams Discovery Hardening (PRE-SPLIT)
- **PR 1** (est. ~400 lines): backend service + config + tasks
- **PR 2** (est. ~300 lines): tests + monitoring integration
- Agent creates PR 1 first, waits for CI, then creates PR 2 on same branch
```

### Step 4.4 — Calculate capacity

```markdown
### Capacity Plan

| Wave | Streams | Parallel agents | Est. duration | Bottleneck |
|------|---------|-----------------|---------------|------------|
| 1    | 6       | 6 Dev + 6 QE    | ~2h           | Stream H (5-8 SP) |
| 2    | 2       | 2 Dev + 2 QE    | ~3h           | Stream E (11 SP) |
```

---

## Phase 5: Execution Plan Output

### Step 5.1 — Produce the plan document

Generate a markdown document following the structure of `$CONFIG.sprint.plans_dir/now-milestone-execution-plan-2026-04-17.md`:

1. **Header**: Plan metadata (date, author, milestone, goal)
2. **Design decision**: Why parallel, what changed since last plan
3. **Worktree design table**: Stream → worktree → issues → SP → touched paths
4. **File-overlap verification**: Explicit confirmation of zero overlap between Wave 1 streams
5. **Dependency graph**: ASCII art or mermaid diagram
6. **Agent team allocation table**: Stream → role → model
7. **Conflict-cutting rules**: (see standard rules below)
8. **Status tracking table**: Wave → Stream → state → branch → PR → depends on → blockers. Always include the leading `Wave` column so sprint-close can filter completion checks per wave. Example template:

   ```markdown
   | Wave | Stream | State | Branch | PR | Depends on | Blockers |
   |------|--------|-------|--------|----|------------|----------|
   | 1    | A      | ready to kick off | feat/... | — | — | none |
   | 1    | B      | ready to kick off | feat/... | — | — | none |
   | 2    | C      | blocked | feat/... | — | Wave 1 | Wave 1 not merged |
   ```

9. **Pre-flight checklist**: Steps to run before spawning agents

### Step 5.2 — Standard conflict-cutting rules (always include)

These rules are inherited from project conventions and must appear in every plan:

1. **Rebase daily**: `git fetch origin && git rebase origin/master` on every active worktree
2. **Migration numbering check before branching**:
   ```bash
   ls backend/migrations/versions/ | tail -1
   ```
   Never create a migration number already in-flight. If two streams both need migrations, pre-assign numbers in the plan.
3. **Overlap check before promoting any new branch to parallel**:
   ```bash
   comm -12 <(gh pr diff NNN --name-only | sort) <(git diff main --name-only | sort)
   ```
   If overlap > 30%, wait for the first PR to merge or merge the branches.
4. **Push review fixes to the PR being reviewed** — never sidecar them onto another active branch
5. **PR titles require `$CONFIG.jira.prefix:` prefix** and conventional commit scope
6. **One concern per PR** even within a worktree — if a stream grows past ~600 line delta, split into separate PRs
7. **Worktree cleanup**: `git worktree remove <path>` immediately after PR merge

### Step 5.3 — Pre-flight checklist (always include)

```markdown
## Pre-flight checklist (do once before spawning agents)

- [ ] `git checkout main && git pull` — clean tree on main
- [ ] Verify no in-flight migrations beyond what's in `master`
- [ ] For each Wave 1 stream, architect agent runs overlap check against current `master`
- [ ] Each Dev agent gets: stream row from table + issue bodies + this plan as context
- [ ] Confirm Docker services healthy: `docker compose ps`
```

---

## Handling Edge Cases

### Edge case: Single large issue dominates the milestone
If one issue touches >50% of the codebase, make it its own stream and schedule it in Wave 1. All other issues that overlap with it go to Wave 2.

### Edge case: All issues overlap
If the overlap matrix shows >30% overlap between most pairs, the milestone is fundamentally sequential. Produce a single-stream plan with internal issue ordering. Flag this to the user: "This milestone is not parallelizable — recommend splitting into smaller milestones or shipping the highest-overlap issues first to unlock parallelism."

### Edge case: Hidden scope doubles an issue's footprint
If a sub-agent's implicit scope discovery adds >5 files to an issue's footprint that weren't in the ticket:
1. Flag this in the plan as "Scope expansion detected"
2. Recommend updating the GitHub issue body with the discovered files
3. Re-run overlap analysis with the expanded footprints

### Edge case: Migration conflicts between streams
If two streams in the same wave both need migrations:
1. Pre-assign migration revision numbers (stream A = N+1, stream B = N+2)
2. Document this in the plan
3. The second agent to branch MUST verify the assignment before creating the migration

### Edge case: Soft edges (shared LOW-risk files)
When two issues share only LOW-risk files (additive changes to config, separate functions in a utility):
1. Flag as "soft edge" in the overlap matrix
2. Default: keep in separate streams
3. Add a note: "If merge conflicts occur on {file}, resolve by accepting both additions"

---

## Validation & Iteration

After producing the plan, validate with:

1. **Overlap sanity check**: For every pair of Wave 1 streams, confirm zero HIGH-risk shared files
2. **Completeness check**: Every milestone issue appears in exactly one stream
3. **Dependency check**: No circular dependencies between streams
4. **Capacity check**: No single wave has more streams than available agent slots
5. **Migration check**: At most one migration per stream, numbers pre-assigned and non-colliding

If validation fails, iterate: merge the conflicting streams, reassign waves, or split the issue causing the conflict.

---

## Output Artifacts

This skill produces:
1. **Execution plan document** → `$CONFIG.sprint.plans_dir/{milestone}-execution-plan-{date}.md`
2. **Overlap matrix** → embedded in the plan (or separate CSV for large milestones)
3. **Issue updates** → if implicit scope discovered, comments added to GitHub issues with discovered files

---

## Related Docs

- `docs/workflows/multi-agent-worktree-workflow.md` — worktree mechanics
- `docs/workflows/worktree-lessons-learned.md` — why concern-based > per-issue
- `docs/workflows/merge-and-review-workflow.md` — PR merge strategy
- `docs/workflows/sprint-skill-chain.md` — full skill chain orchestration
- `docs/AGENT-MODEL-SELECTION.md` — model tier allocation
- `.claude/skills/backlog-groom/SKILL.md` — issue hygiene (run before this skill)
- `.claude/skills/create-issue/SKILL.md` — if scope expansion requires new issues

---

## On Complete

When this skill finishes producing the execution plan:

1. **Tell the user**: "Execution plan saved to `$CONFIG.sprint.plans_dir/{file}`. Ready to create worktrees and launch agents."
2. **Suggest next skill**: `/sprint-kickoff --plan $CONFIG.sprint.plans_dir/{file} --wave 1`
3. **Pass forward**: The plan document path is the only argument needed — `/sprint-kickoff` parses it for stream definitions, worktree names, and agent prompts.
