---
name: backlog-groom
description: Audit the open GitHub issue backlog for staleness, duplicates, missing labels/milestones, and natural sprint groupings. Produces an actionable report and optionally applies fixes.
argument-hint: "[--apply | --report-only | --focus <area>]"
allowed-tools: Bash(gh *) Bash(git *) Bash(python *) Read Write Glob Grep Agent TodoWrite
---

# Backlog Grooming: Systematic Issue Hygiene & Sprint Discovery

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Audit all open issues in `$CONFIG.repo` against the codebase, detect problems, and optionally fix them.

---

## Repository & Project Constants

```
REPO          = $CONFIG.repo
PROJECT_NUMBER = $CONFIG.github.project_number
MILESTONES    = Now (current sprint), Next (1-2 sprints), Later (backlog), Icebox (aspirational)
```

---

## Invocation Modes

### Mode 1: Full Audit (default)
```
/backlog-groom
```
Run all 6 checks below, produce a report, and ask before applying fixes.

### Mode 2: Apply Fixes
```
/backlog-groom --apply
```
Run all checks and apply fixes (close stale, merge duplicates, assign milestones) with comments on each issue.

### Mode 3: Report Only
```
/backlog-groom --report-only
```
Produce the report without modifying any issues.

### Mode 4: Focus Area
```
/backlog-groom --focus redis
/backlog-groom --focus admin
```
Audit only issues matching the given keyword/label.

---

## The 6 Checks

### Check 1: Stale Issue Detection

For each open issue, determine if it's been **superseded by shipped work**.

**Method:**
1. Pull all open issues: `gh issue list --state open --limit 200 --json number,title,labels,body,createdAt`
2. Identify issues with sprint-labeled or plan-derived prefixes: `[user-teams]`, `Sprint N:`, `Task N:`, `Phase N`
3. For each candidate, check if the described feature exists in the codebase:
   - Search for mentioned files, endpoints, components, migrations
   - Compare acceptance criteria against actual implementation
4. Classify as: `stale` (all ACs met), `partial` (some ACs met), or `active` (work still needed)

**Output:**
```markdown
### Stale Issues (safe to close)
| # | Title | Reason | Missing ACs |
|---|-------|--------|-------------|

### Partially Complete (extract follow-ups before closing)
| # | Title | Implemented | Still Missing |
|---|-------|------------|---------------|
```

**Important:** For `partial` issues, extract missing ACs into new follow-up issues before closing.

### Check 2: Duplicate & Overlap Detection

**Method:**
1. Compare issue titles using word overlap (threshold: 4+ shared meaningful words)
2. Group issues by concern area using keyword matching:
   - Redis/leaks, Monitoring/observability, Security/auth, Testing/CI, Admin UI, K8s/deploy, etc.
3. Within each group, check for issues that describe the same work differently
4. Flag umbrella issues that should absorb smaller scoped issues

**Output:**
```markdown
### Duplicates (close the smaller, keep the umbrella)
| Close | Keep | Reason |
|-------|------|--------|

### Overlaps (review — may be intentional phases)
| Issue A | Issue B | Shared Scope |
|---------|---------|-------------|
```

### Check 3: Missing Labels & Priority

Every issue must have:
- At least 1 **component label** (`frontend`, `backend`, `database`, `infrastructure`)
- At least 1 **category label** (`bug`, `enhancement`, `testing`, `documentation`, `performance`)
- A **priority** (P0-P3) — check both the GitHub label AND the project board Priority field

**Output:**
```markdown
### Missing Labels
| # | Title | Missing |
|---|-------|---------|

### Missing Priority (no P0-P3 label AND no board Priority)
| # | Title |
|---|-------|
```

### Check 4: Missing Milestones

Every open issue should belong to a milestone: `Now`, `Next`, `Later`, or `Icebox`.

**Output:**
```markdown
### No Milestone Assigned
| # | Title | Suggested Milestone | Reason |
|---|-------|--------------------|---------| 
```

**Suggestion logic:**
- P0/P1 with clear scope -> `Now`
- P1/P2 with dependencies or medium scope -> `Next`
- P2/P3 marked `could-have` -> `Later`
- `[enterprise-scale]` prefix -> `Icebox`

### Check 5: Naming Convention Violations

Issue titles should follow the **conventional commit** style used in PR titles:
- `feat(scope):`, `fix(scope):`, `chore(scope):`, `test(scope):`, `docs:`
- Sprint work must include `$CONFIG.jira.prefix:` prefix

Flag issues using legacy prefixes:
- `[user-teams]`, `Task N:`, `Sprint N:`, `[Enhancement]`, `[UI]`, `[Storybook]`, `[P1]`

**Output:**
```markdown
### Naming Convention Violations
| # | Current Title | Suggested Title |
|---|---------------|-----------------|
```

### Check 6: Age & Staleness Risk

Flag issues older than 6 weeks with no linked PRs, no recent comments, and no milestone.

**Output:**
```markdown
### At Risk (old, unlinked, unmilestoned)
| # | Title | Age | Last Activity |
|---|-------|-----|---------------|
```

---

## Applying Fixes

When `--apply` is used (or user confirms), apply these changes:

### Closing stale issues
```bash
gh issue close <NUMBER> --repo $CONFIG.repo \
  --comment "**Closing -- implemented and verified.** <reason>. Verified via backlog grooming audit on <date>."
```

### Merging duplicates
```bash
# Close the absorbed issue
gh issue close <NUMBER> --repo $CONFIG.repo \
  --comment "**Closing -- absorbed into #<PARENT>.** <reason>. Backlog audit <date>."

# Comment on the parent issue
gh issue comment <PARENT> --repo $CONFIG.repo \
  --body "**Backlog audit <date>:** #<ABSORBED> has been absorbed into this issue. ACs from that issue should be addressed as part of this work."
```

### Assigning milestones
```bash
gh issue edit <NUMBER> --repo $CONFIG.repo --milestone "<milestone>"
```

### Fixing labels (add missing)
```bash
gh issue edit <NUMBER> --repo $CONFIG.repo --add-label "<label>"
```

---

## Report Summary

At the end, produce a summary:

```markdown
## Backlog Grooming Summary -- <date>

| Metric | Before | After |
|--------|--------|-------|
| Open issues | NN | NN |
| Stale closed | -- | NN |
| Duplicates merged | -- | NN |
| Follow-ups created | -- | NN |
| Missing milestones | NN | 0 |
| Missing labels | NN | 0 |
| Missing priority | NN | NN |

### Milestone Distribution
| Milestone | Count |
|-----------|-------|
| Now | NN |
| Next | NN |
| Later | NN |
| Icebox | NN |
| None | NN |

### Concern Area Clusters
<list top 5 areas by issue count>

### Recommended Next Sprint
<top N issues from "Now" milestone, grouped by concern area>
```

---

## Critical Rules

1. **NEVER close an issue without verifying ACs against the codebase.** Use `Grep`, `Glob`, and `Read` to check.
2. **For partial implementations**, extract missing ACs into new follow-up issues via `/create-issue` before closing.
3. **Always add a comment** explaining why an issue is being closed or absorbed.
4. **Present the report and wait for confirmation** before applying destructive changes (closes, merges).
5. **Check for PRs linked to issues** before closing -- an open PR means active work.
6. **Milestone assignment is non-destructive** -- apply these without confirmation when `--apply` is set.

---

## On Complete

When the grooming report is generated and fixes are applied:

1. **Tell the user**: "Backlog grooming complete. {N} issues closed, {M} duplicates merged, {K} milestones assigned."
2. **Suggest next skill based on context**:
   - If the user is starting a sprint: "Backlog is clean. Run `/plan-parallel-streams --milestone {milestone}` to plan the parallel execution."
   - If the user is doing periodic maintenance: "Grooming done. Run `/branch-cleanup` to also clean up stale remote branches."
3. **Pass forward**: The grooming report's "Recommended Next Sprint" section identifies the top issues for `/plan-parallel-streams`.
