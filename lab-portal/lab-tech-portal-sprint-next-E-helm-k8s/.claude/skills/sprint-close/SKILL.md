---
name: sprint-close
description: Close a PR's linked issues, remove its worktree, delete the remote branch, update the plan status table, and check wave completion. Standardizes the post-merge lifecycle that was previously manual.
argument-hint: "<pr-number> [--wave N] [--plan <plan.md>] [--batch <pr1,pr2,...>] [--check] [--no-pr]"
allowed-tools: Bash(gh *) Bash(git *) Bash(jq *) Bash(date *) Bash(cat *) Bash(sed *) Bash(echo *) Bash(grep *) Bash(sort *) Bash(tr *) Bash(head *) Bash(ls *) Bash(python3 *) Read Write Glob Grep TodoWrite
---

# Sprint Close: Post-Merge Lifecycle Automation

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

After a PR is merged via GitHub UI, this skill closes linked issues, removes the worktree, cleans up the branch, updates the plan status, and checks if the wave is complete.

---

## Why This Skill Exists

**Problem**: After every PR merge, the operator must manually:
1. Close linked GitHub issues with a comment referencing the PR
2. Remove the git worktree
3. Delete the remote branch
4. Update the plan status table from "in-progress" to "merged"
5. Check if all streams in the wave are done
6. Write a changelog entry

For a 6-stream wave, that's 36+ manual steps. Forgetting any creates drift — stale worktrees on disk, open issues for shipped work, outdated plan status, branch sprawl.

**Solution**: One command per merged PR. Batch mode for closing an entire wave at once.

---

## Repository & Project Constants

```
REPO          = $CONFIG.repo
PROJECT_ROOT  = $(git rev-parse --show-toplevel)
WORKTREE_ROOT = $(dirname "$(git rev-parse --show-toplevel)")  # $CONFIG.worktree.root — parent of repo root
```

---

## Invocation Modes

### Mode 1: Single PR (default)
```
/sprint-close 640
```
Close everything associated with PR #640.

### Mode 2: Batch (whole wave)
```
/sprint-close --batch 630,631,632,633,634,635
```
Close all PRs in sequence. Useful after a wave completes.

### Mode 3: With plan reference
```
/sprint-close 640 --plan $CONFIG.sprint.plans_dir/now-milestone-execution-plan-2026-04-17.md
```
Also update the specified plan document's status table.

### Mode 4: Wave completion check only
```
/sprint-close --wave 1 --plan $CONFIG.sprint.plans_dir/X.md --check
```
Don't close anything — just check if all Wave 1 streams are merged and report readiness for Wave 2.

---

## Phase 1: Gather PR Context

### Step 1.1 — Fetch PR metadata

```bash
PR_DATA=$(gh pr view $PR_NUMBER \
  --repo $CONFIG.repo \
  --json number,title,state,mergedAt,headRefName,body,closingIssuesReferences)

echo "$PR_DATA" | jq '.'
```

### Step 1.2 — Validate PR is merged

```bash
STATE=$(echo "$PR_DATA" | jq -r '.state')
if [[ "$STATE" != "MERGED" ]]; then
  echo "ERROR: PR #${PR_NUMBER} is ${STATE}, not MERGED. Cannot close."
  echo "Merge the PR first via GitHub UI, then retry."
  exit 1
fi
```

### Step 1.3 — Extract linked issues

```bash
# From PR body "Closes #NNN" references
LINKED_ISSUES=$(echo "$PR_DATA" | jq -r '.closingIssuesReferences[].number')

# Also search PR body for manual references (portable: no PCRE -P flag)
BODY_ISSUES=$(echo "$PR_DATA" | jq -r '.body' | grep -oE '#[0-9]+' | tr -d '#' | sort -u)

# Combine and deduplicate
ALL_ISSUES=$(echo -e "${LINKED_ISSUES}\n${BODY_ISSUES}" | sort -u | grep -v '^$')
echo "Linked issues: ${ALL_ISSUES}"
```

### Step 1.4 — Identify the branch and worktree

```bash
BRANCH=$(echo "$PR_DATA" | jq -r '.headRefName')
MERGED_AT=$(echo "$PR_DATA" | jq -r '.mergedAt')

# Find the worktree for this branch
WORKTREE_PATH=$(git worktree list --porcelain | grep -B1 "branch refs/heads/${BRANCH}" | head -1 | sed 's/worktree //')
echo "Branch: ${BRANCH}"
echo "Worktree: ${WORKTREE_PATH:-'(not found — already removed or different machine)'}"
```

---

## Phase 2: Close Linked Issues

### Step 2.1 — Close each linked issue

For each issue number in `ALL_ISSUES`:

```bash
for ISSUE in ${ALL_ISSUES}; do
  # Check if already closed
  ISSUE_STATE=$(gh issue view "${ISSUE}" --repo $CONFIG.repo --json state --jq '.state')

  if [[ "$ISSUE_STATE" == "CLOSED" ]]; then
    echo "  ✓ Issue #${ISSUE} already closed"
    continue
  fi

  gh issue close "${ISSUE}" \
    --repo $CONFIG.repo \
    --comment "Shipped in PR #${PR_NUMBER} (merged ${MERGED_AT}). Closed by /sprint-close."

  echo "  ✓ Closed issue #${ISSUE}"
done
```

### Step 2.2 — Update project board status

For issues that were on the project board, update Status to "Done":

```bash
# Fetch PROJECT_ID once outside the loop — it is constant across all issues
PROJECT_ID=$(gh api graphql -f query='{ organization(login: "$CONFIG.github.org") { projectV2(number: $CONFIG.github.project_number) { id } } }' --jq '.data.organization.projectV2.id')

for ISSUE in ${ALL_ISSUES}; do
  ISSUE_NODE_ID=$(gh issue view "${ISSUE}" --repo $CONFIG.repo --json id --jq '.id')

  # Find the item on the project board via the issue's own projectItems relationship
  ITEM_ID=$(gh api graphql \
    -f query='query($content: ID!) { node(id: $content) { ... on Issue { projectItems(first: 10) { nodes { id project { ... on ProjectV2 { number } } } } } } }' \
    -f content="$ISSUE_NODE_ID" \
    --jq ".data.node.projectItems.nodes[] | select(.project.number == $CONFIG.github.project_number) | .id")

  if [[ -n "$ITEM_ID" ]]; then
    # Status field: $CONFIG.github.status_field_id, Done = $CONFIG.github.status_options.done
    gh api graphql \
      -f query='mutation($project: ID!, $item: ID!, $field: ID!, $value: String!) { updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: {singleSelectOptionId: $value}}) { projectV2Item { id } } }' \
      -f project="$PROJECT_ID" \
      -f item="$ITEM_ID" \
      -f field="$CONFIG.github.status_field_id" \
      -f value="$CONFIG.github.status_options.done"
    echo "  ✓ Updated board status to Done for #${ISSUE}"
  fi
done
```

---

## Phase 3: Remove Worktree

### Step 3.1 — Check for uncommitted changes

```bash
if [[ -n "$WORKTREE_PATH" && -d "$WORKTREE_PATH" ]]; then
  DIRTY=$(git -C "${WORKTREE_PATH}" status --porcelain)
  if [[ -n "$DIRTY" ]]; then
    echo "WARNING: Worktree has uncommitted changes:"
    echo "$DIRTY"
    echo ""
    echo "These changes will be LOST. Proceed? (The PR is already merged, so this is usually safe.)"
    # Wait for confirmation before removing
  fi
fi
```

### Step 3.2 — Remove the worktree

```bash
if [[ -n "$WORKTREE_PATH" && -d "$WORKTREE_PATH" ]]; then
  git worktree remove "${WORKTREE_PATH}" --force
  echo "✓ Removed worktree: ${WORKTREE_PATH}"
else
  echo "ℹ No local worktree found for branch ${BRANCH} — may have been removed already or created on another machine."
fi
```

---

## Phase 4: Delete Remote Branch

### Step 4.1 — Delete the remote branch

```bash
# Check if branch still exists on remote
if git ls-remote --heads origin "${BRANCH}" | grep -q "${BRANCH}"; then
  git push origin --delete "${BRANCH}"
  echo "✓ Deleted remote branch: ${BRANCH}"
else
  echo "ℹ Remote branch ${BRANCH} already deleted (auto-delete on merge is enabled)."
fi
```

### Step 4.2 — Prune local tracking ref

```bash
git fetch --prune origin
git branch -D "${BRANCH}" 2>/dev/null || true
echo "✓ Pruned local tracking refs"
```

---

## Phase 5: Update Plan Status

### Step 5.1 — Find and update the plan document

If `--plan` was specified, use that. Otherwise, find the most recent plan:

```bash
# Widen glob to cover both naming conventions (*-execution-plan-*.md and *-parallel-streams-*.md)
PLAN_FILE="${PLAN_ARG:-$(ls -t $CONFIG.sprint.plans_dir/*.md 2>/dev/null | head -1)}"
if [[ -z "$PLAN_FILE" ]]; then
  echo "ERROR: No plan file found and --plan not specified. Pass --plan <path> explicitly."
  exit 1
fi
```

### Step 5.2 — Update the status table

Find the stream row matching this PR's branch name and update its state:

```
Before: | A | #598, #597 | in-progress | feat/now-A-admin-polish | #630 | — |
After:  | A | #598, #597 | **merged** | feat/now-A-admin-polish | #630 | — |
```

Use sed or a targeted edit to change the state column. If the PR number isn't in the table yet, add it.

### Step 5.3 — Commit the plan update

```bash
cd "${PROJECT_ROOT}"
git add $CONFIG.sprint.plans_dir/
git commit -m "docs: update plan status — PR #${PR_NUMBER} merged (Stream ${STREAM_ID})"
```

---

## Phase 6: Wave Completion Check

### Step 6.1 — Count wave status

Read the plan's status table and count streams by state for the current wave. When the status table has a leading `Wave` column (format produced by `plan-parallel-streams` Step 5.1), filter rows by the target wave number before counting. Fall back to scanning all stream rows for older single-wave plans that lack the column.

```bash
WAVE_NUMBER="${WAVE_ARG:-1}"

# Extract only the Status tracking table section from the plan file.
# The status table is identified by having BOTH "Wave" AND "Stream" AND "State" columns
# in its header row (unique to the status table; the Capacity Plan table has Wave but
# not Stream+State together). Slice from that header line to the next markdown heading.
STATUS_TABLE=$(awk '
  /^\|[[:space:]]*Wave[[:space:]]*\|[[:space:]]*Stream[[:space:]]*\|[[:space:]]*State[[:space:]]*\|/ { in_table=1 }
  in_table && /^#/ { in_table=0 }
  in_table { print }
' "$PLAN_FILE")

# Detect whether the extracted section has a Wave column (it will if STATUS_TABLE is non-empty)
if [[ -n "$STATUS_TABLE" ]]; then
  # New format: filter rows where the first column equals the target wave number
  WAVE_ROWS=$(echo "$STATUS_TABLE" | grep -E "^\|\s*${WAVE_NUMBER}\s*\|")
else
  # Legacy single-wave format: use all stream rows (non-header, non-separator)
  WAVE_ROWS=$(grep -E '^\|' "$PLAN_FILE" | grep -v -E '^\|[-| ]+\|$' | grep -v -iE '^\|\s*(Wave|Stream|---)')
fi

TOTAL=$(echo "$WAVE_ROWS" | grep -c '.' || true)
MERGED=$(echo "$WAVE_ROWS" | grep -ic '\*\*merged\*\*\|merged' || true)
REMAINING=$(( TOTAL - MERGED ))
```

Report format:

```markdown
### Wave {N} Status
- ✓ Stream A — merged (PR #630)
- ✓ Stream B — merged (PR #631)
- ✓ Stream C — merged (PR #632)
- ✓ Stream D — merged (PR #633)
- ✓ Stream G — merged (PR #634)
- ✗ Stream H — in-progress (PR #635, awaiting review)

Wave {N}: 5/6 merged. 1 remaining.
```

### Step 6.2 — If wave complete, suggest next wave

If all streams in the wave are merged:

```markdown
## 🎉 Wave {N} Complete!

All {M} streams merged successfully.

### Next steps:
1. **Wave {N+1}** has {K} streams ready to start.
2. Run: `/sprint-kickoff --plan {plan_file} --wave {N+1}`
3. Gating dependencies (if any):
   - Stream F was waiting on Stream G — ✓ now unblocked
```

### Step 6.3 — If milestone complete, suggest cleanup

If no more waves remain:

```markdown
## Milestone "{MILESTONE}" Complete!

All waves merged. Final cleanup:
1. Run `/branch-cleanup --apply` to delete any remaining stale branches
2. Run `/backlog-groom --apply` to verify no open issues remain for this milestone
3. Write the sprint retrospective in `changelogs/`
```

---

## Phase 6.5: Guide-Friction Sync (slice-close only)

### Step 6.5 — Guide-friction sync (slice-close or friction-file-modified)

Two triggers independently invoke `/guide-friction-sync --no-pr`:

1. **Slice-label exhaustion** (existing): all issues for the PR's slice label are now closed.
2. **Friction file modified** (new): the merged PR directly modified `$CONFIG.sprint.friction_file`.

Either condition is sufficient. Check both:

```bash
# --- Trigger 1: did the merged PR touch $CONFIG.sprint.friction_file? ---
PR_TOUCHED_FRICTION=$(gh pr view "$PR_NUMBER" \
  --repo $CONFIG.repo \
  --json files \
  --jq '[.files[].path] | any(. == "$CONFIG.sprint.friction_file")')

# --- Trigger 2: slice-label exhaustion ---
SLICE_LABEL=$(gh pr view "$PR_NUMBER" \
  --repo $CONFIG.repo \
  --json labels \
  --jq '.labels[] | select(.name | startswith("$CONFIG.labels.slice_prefix")) | .name' | head -1)

REMAINING=-1  # sentinel: no slice label present
if [[ -n "$SLICE_LABEL" ]]; then
  REMAINING=$(gh issue list \
    --repo $CONFIG.repo \
    --label "$SLICE_LABEL" \
    --state open \
    --json number \
    --jq 'length')

  if [[ "$REMAINING" -eq 0 ]]; then
    echo "All issues for slice '${SLICE_LABEL}' are now closed."
  else
    echo "Slice '${SLICE_LABEL}' still has ${REMAINING} open issue(s)."
  fi
fi

# --- Decide whether to run sync ---
if [[ "$PR_TOUCHED_FRICTION" == "true" ]] || [[ "$REMAINING" -eq 0 ]]; then
  echo "Guide-friction-sync triggered (friction-file-modified=${PR_TOUCHED_FRICTION}, slice-exhausted=$([[ "$REMAINING" -eq 0 ]] && echo true || echo false))."
  # invoke guide-friction-sync --no-pr
else
  echo "Skipping guide-friction-sync (no slice exhausted, friction file not modified)."
fi
```

**When the sync runs**: invoke the `/guide-friction-sync` skill with the `--no-pr` flag (use the Skill tool: `Skill({ skill: "guide-friction-sync", args: "--no-pr" })`). This runs all phases but skips Phase 5's PR-creation step; the resulting `$CONFIG.sprint.friction_file` change is staged and folded into the plan-status commit below.

If `/guide-friction-sync --no-pr` produces changes, include them in the plan-status commit (Step 5.3) or add it immediately after. The combined commit message should note both changes:

```
docs: update plan status — PR #${PR_NUMBER} merged (Stream ${STREAM_ID}); guide-friction sync — tracked F0X, F0Y
```

See [.claude/skills/guide-friction-sync/SKILL.md](../guide-friction-sync/SKILL.md) for the full skill documentation.

---

## Phase 7: Changelog Stub (Optional)

### Step 7.1 — Generate a changelog entry

If the user requested changelog generation (or if closing the last PR in a wave):

```markdown
# Changelog — {DATE}

## {MILESTONE} Milestone — Wave {N}

### Merged PRs
| PR | Title | Stream | Issues Closed |
|----|-------|--------|---------------|
| #630 | $CONFIG.jira.prefix: fix(admin): polish VideoQE inline edit | A | #597, #598 |
| #631 | $CONFIG.jira.prefix: feat(discovery): team pagination | B | #596 |
| ... | ... | ... | ... |

### Technical Decisions
- {leave blank for operator to fill}

### Lessons Learned
- {leave blank for operator to fill}
```

Save to `changelogs/{date}.md` if it doesn't exist; append if it does.

---

## Error Handling

### PR not found
```
ERROR: PR #999 not found. Verify the number: gh pr view 999
```

### PR not merged
```
ERROR: PR #640 is OPEN (not merged). Merge it via GitHub UI first, then retry.
If the PR should be closed without merge: gh pr close 640
```

### Worktree has diverged changes
If the worktree branch has commits not in the merged PR (e.g., agent made extra commits after the PR was created):
1. List the extra commits
2. Ask: "These commits were NOT in the merged PR. Discard them?"
3. Only remove worktree after confirmation

---

## Related Docs

- `docs/workflows/sprint-skill-chain.md` — full workflow chain
- `.claude/skills/sprint-kickoff/SKILL.md` — creates what this skill removes
- `.claude/skills/review-pr/SKILL.md` — runs before merge, which runs before this
- `.claude/skills/branch-cleanup/SKILL.md` — bulk cleanup (this skill is per-PR)

---

## On Complete

When the PR is fully closed (issues closed, worktree removed, branch deleted, plan updated):

1. **Report what was done**:
   - "PR #{N} closed. Issues #{X}, #{Y} closed. Worktree removed. Branch deleted. Plan updated."
2. **If more streams remain in the wave**:
   - "Wave {W}: {done}/{total} merged. {remaining} streams still in progress."
   - "After the next PR merges, run `/sprint-close <PR#>`."
3. **If wave is complete**:
   - "Wave {W} complete! Run `/sprint-kickoff --plan {file} --wave {W+1}` to start the next wave."
4. **If milestone is complete**:
   - "Milestone done! Run `/branch-cleanup --apply` for final cleanup, then `/backlog-groom` for the next cycle."
