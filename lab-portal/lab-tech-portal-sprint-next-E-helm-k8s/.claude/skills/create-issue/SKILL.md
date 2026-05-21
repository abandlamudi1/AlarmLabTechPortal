---
name: create-issue
description: Create well-structured GitHub issues and add them to project board with correct Priority, Size, Status, and labels. Use for plan-to-issue translation, proactive issue capture, and backlog grooming.
argument-hint: "[--batch plan.json | --title 'Issue title']"
allowed-tools: Bash(gh *) Bash(git *) Bash(python *) Bash(node *) Read Write Glob Grep Agent TodoWrite
---

# Create Issue: Standardized GitHub Issue Creation & Project Board Integration

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Create one or more GitHub issues in `$CONFIG.repo` and add them to **Project Board #$CONFIG.github.project_number** with all custom fields populated.

---

## Quick Reference: Invocation Modes

### Mode 1: Interactive (from conversation)
The user describes a task or you identify an issue to create during sprint work.
Gather the required fields via conversation context and create the issue.

### Mode 2: Batch (from plan)
```
/create-issue --batch
```
The user has a plan (sprint plan, audit, or feature spec) and wants to translate ALL actionable items into issues. Parse the plan, generate the issue list, present for confirmation, then create all.

### Mode 3: Single with title
```
/create-issue --title "feat: add Redis connection pooling"
```
Create a single issue with the given title. Infer labels, priority, and size from context.

---

## Repository & Project Constants

```
REPO_OWNER    = adc-quality  (derived from $CONFIG.repo)
REPO_NAME     = lab-tech-portal  (derived from $CONFIG.repo)
REPO          = $CONFIG.repo
PROJECT_NUMBER = $CONFIG.github.project_number
```

---

## Step 1: Gather Issue Data

For each issue to create, collect these fields:

| Field | Required | Source |
|---|---|---|
| Title | YES | Must include `$CONFIG.jira.prefix:` prefix for sprint work; omit prefix only for standalone backlog items |
| Body | YES | Use the **Issue Body Template** below |
| Labels | YES | At least one component label + one category label (see **Valid Labels**) |
| Priority | YES | P0, P1, P2, P3, or P4 (see **Priority Guide**) |
| Size | YES | XS, S, M, L, or XL (see **Size Guide**) |
| Status | NO | Defaults to "Todo". Re-categorize on the project board UI after creation if needed (the In progress / Done transitions are handled by other skills). |

---

## Step 2: Issue Body Template

Use this standardized template for ALL issues. Omit sections that don't apply, but always include Goal, Acceptance Criteria, and Story Points.

```markdown
## Goal

<1-3 sentences: what this achieves and why it matters>

## Acceptance Criteria

- [ ] <specific, testable criterion>
- [ ] <specific, testable criterion>
- [ ] <specific, testable criterion>

## Technical Details

<Optional: architecture notes, code snippets, migration SQL, API contracts>

## Files to Modify

- `path/to/file.py` — <what changes>
- `path/to/component.tsx` — <what changes>

## Dependencies

- Depends on #NNN (if applicable)
- Blocked by: <description> (if applicable)

## Story Points

<number: 1, 2, 3, 5, 8, 13>

## Testing

- [ ] <unit test requirement>
- [ ] <integration test requirement>
- [ ] <manual verification needed? → call it out explicitly in the AC>
```

---

## Step 3: Validate Before Creating

Before creating, present a summary table and **wait for user confirmation**:

```markdown
| # | Title | Priority | Size | Labels | SP |
|---|-------|----------|------|--------|----|
| 1 | ...   | P1       | M    | ...    | 3  |
| 2 | ...   | P2       | S    | ...    | 2  |
```

**Total story points: NN**

Only proceed after the user confirms.

---

## Step 4: Create Issue

### 4a. Create the issue
```bash
gh issue create \
  --repo $CONFIG.repo \
  --title "<title>" \
  --label "<label1>,<label2>" \
  --body "<body>"
```

Capture the issue number from the output.

### 4b. Add to Project Board #$CONFIG.github.project_number
```bash
# Get the issue node ID
ISSUE_NODE_ID=$(gh issue view <NUMBER> --repo $CONFIG.repo --json id --jq '.id')

# Get project ID
PROJECT_ID=$(gh api graphql -f query='{ organization(login: "$CONFIG.github.org") { projectV2(number: $CONFIG.github.project_number) { id } } }' --jq '.data.organization.projectV2.id')

# Add issue to project
ITEM_ID=$(gh api graphql \
  -f query='mutation($project: ID!, $content: ID!) { addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }' \
  -f project="$PROJECT_ID" \
  -f content="$ISSUE_NODE_ID" \
  --jq '.data.addProjectV2ItemById.item.id')
```

### 4c. Set Priority field
```bash
# Priority field ID: $CONFIG.github.priority_field_id
# Option IDs:
#   P0 = $CONFIG.github.priority_options.p0
#   P1 = $CONFIG.github.priority_options.p1
#   P2 = $CONFIG.github.priority_options.p2
#   P3 = $CONFIG.github.priority_options.p3
#   P4 = $CONFIG.github.priority_options.p4

gh api graphql \
  -f query='mutation($project: ID!, $item: ID!, $field: ID!, $value: String!) { updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: {singleSelectOptionId: $value}}) { projectV2Item { id } } }' \
  -f project="$PROJECT_ID" \
  -f item="$ITEM_ID" \
  -f field="$CONFIG.github.priority_field_id" \
  -f value="<PRIORITY_OPTION_ID>"
```

### 4d. Set Size field
```bash
# Size field ID: $CONFIG.github.size_field_id
# Option IDs:
#   XS = $CONFIG.github.size_options.xs
#   S  = $CONFIG.github.size_options.s
#   M  = $CONFIG.github.size_options.m
#   L  = $CONFIG.github.size_options.l
#   XL = $CONFIG.github.size_options.xl

gh api graphql \
  -f query='mutation($project: ID!, $item: ID!, $field: ID!, $value: String!) { updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: {singleSelectOptionId: $value}}) { projectV2Item { id } } }' \
  -f project="$PROJECT_ID" \
  -f item="$ITEM_ID" \
  -f field="$CONFIG.github.size_field_id" \
  -f value="<SIZE_OPTION_ID>"
```

### 4e. Set Status field (if not default "Todo")
```bash
# Status field ID: $CONFIG.github.status_field_id
# Option IDs (Project #23 status field — only these three options exist; do not
# hardcode `blocked` / `todo_manual` option IDs that were valid on Project #26):
#   Todo        = $CONFIG.github.status_options.todo
#   In progress = $CONFIG.github.status_options.in_progress
#   Done        = $CONFIG.github.status_options.done

gh api graphql \
  -f query='mutation($project: ID!, $item: ID!, $field: ID!, $value: String!) { updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: {singleSelectOptionId: $value}}) { projectV2Item { id } } }' \
  -f project="$PROJECT_ID" \
  -f item="$ITEM_ID" \
  -f field="$CONFIG.github.status_field_id" \
  -f value="<STATUS_OPTION_ID>"
```

---

## Step 5: Report Results

After creating all issues, output a summary:

```markdown
## Issues Created

| # | Issue | Title | Priority | Size | Status | SP |
|---|-------|-------|----------|------|--------|----|
| 1 | #NNN  | ...   | P1       | M    | Todo   | 3  |
| 2 | #NNN  | ...   | P2       | S    | Todo   | 2  |

**Total: N issues, NN story points**
**Project board:** https://github.com/orgs/$CONFIG.github.org/projects/$CONFIG.github.project_number
```

---

## Valid Labels

### Component labels (pick at least one)
| Label | Description |
|---|---|
| `frontend` | Frontend (React/TypeScript) |
| `backend` | Backend (FastAPI/Python) |
| `database` | Database schema and migrations |
| `infrastructure` | Infrastructure / DevOps |

### Category labels (pick at least one)
| Label | Description |
|---|---|
| `bug` | Something isn't working |
| `enhancement` | New feature or request |
| `documentation` | Docs improvements |
| `performance` | Performance optimization |
| `testing` | Unit/integration/E2E tests |

### Scope labels (pick if applicable)
| Label | Description |
|---|---|
| `api` | REST API endpoints |
| `models` | SQLAlchemy model definitions |
| `admin` | Admin UI components |
| `dashboard` | Dashboard components |
| `kanban` | Kanban board components |
| `navigation` | Navigation and routing |
| `react` | React components |
| `hooks` | React hooks |
| `types` | TypeScript type definitions |
| `rbac` | Role-based access control |
| `celery` | Celery background tasks |
| `teams` | Microsoft Teams integration |
| `jira` | JIRA integration |
| `alerts` | Alerts page enhancements |
| `e2e` | End-to-end Playwright tests |
| `tests` | Unit/integration tests |
| `docs` | Documentation |

### Sprint/phase labels (add for sprint-scoped work)
| Label | Pattern |
|---|---|
| `sprint-N` | e.g., `sprint-12`, `sprint-13` |
| `phase-X` | e.g., `phase-E`, `phase-F` |
| `User_sprint_N` | User management phases |
| `Rate_limit_sprint_1` | Rate limiting work |

### Backlog labels
| Label | Use when |
|---|---|
| `future` | Enhancement for later consideration |
| `backlog` | Backlog items not yet prioritized |

---

## Priority Guide

| Priority | Meaning | Examples |
|---|---|---|
| **P0** | Critical / blocking | Production crash, security vuln, data corruption, blocks all other work |
| **P1** | High / this sprint | Core feature for current sprint, significant bug affecting users |
| **P2** | Medium / next sprint | Enhancement, non-blocking bug, tech debt with growing impact |
| **P3** | Low / backlog | Nice-to-have, cosmetic, future consideration |
| **P4** | Icebox / aspirational | Speculative ideas, exploratory tooling, long-tail polish — flag for re-evaluation rather than implementation |

---

## Size Guide (maps to story points)

| Size | Story Points | Guideline |
|---|---|---|
| **XS** | 1 | Config change, typo fix, single-line edit |
| **S** | 2 | Single-file change, straightforward logic |
| **M** | 3-5 | Multi-file change, new component or endpoint |
| **L** | 8 | Cross-cutting feature, requires tests + migrations |
| **XL** | 13 | Major feature, multiple services, significant testing |

---

## Batch Mode: Plan-to-Issues Translation

When invoked with `--batch`, follow this workflow:

1. **Ask** the user which plan file to parse (or use the current plan from the conversation)
2. **Parse** the plan into discrete, actionable items
3. **For each item**, infer: title, labels, priority, size, body content
4. **Present** the full table for review (Step 3 above)
5. **After confirmation**, create all issues sequentially (to avoid rate limits)
6. **Report** the full summary with issue numbers

### Batch rules
- Check for existing issues with similar titles before creating (avoid duplicates)
- If creating > 10 issues, batch in groups of 5 with a brief pause between groups
- Each issue must be independently actionable (no "meta" issues that just group others)

---

## Critical Rules

1. **ALWAYS present the summary table and wait for confirmation** before creating any issues.
2. **ALWAYS set Priority and Size** on the project board — these are the fields that were inconsistently set before.
3. **ALWAYS include at least one component label** (`frontend`, `backend`, `database`, `infrastructure`) and one category label (`bug`, `enhancement`, etc.).
4. **NEVER create duplicate issues.** Check existing open issues first: `gh issue list --repo $CONFIG.repo --state open --search "<title keywords>" --limit 5`
5. **Use the standardized body template.** Goal + Acceptance Criteria + Story Points are mandatory sections.
6. **Sprint work titles** must include `$CONFIG.jira.prefix:` prefix.
7. **Story points must match Size**: XS=1, S=2, M=3-5, L=8, XL=13. If they don't align, flag the mismatch.

---

## On Complete

When issues are created and added to the project board:

1. **Tell the user**: "{N} issues created ({SP} total story points). All added to Project Board #$CONFIG.github.project_number."
2. **Suggest next skill based on context**:
   - If creating issues for a sprint plan: "Issues created. Run `/plan-parallel-streams --issues {comma-separated-numbers}` to plan the parallel execution."
   - If creating follow-up issues during grooming: "Follow-up issues created. Continue with `/backlog-groom` or proceed to sprint planning."
   - If capturing proactive ideas: "Issues captured in backlog. No immediate action needed."
3. **Pass forward**: The created issue numbers are the input to `/plan-parallel-streams`.
