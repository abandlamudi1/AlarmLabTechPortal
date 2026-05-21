---
name: branch-cleanup
description: Audit and delete stale remote branches (merged or abandoned) in the lab-tech-portal repo. Handles the squash/rebase-merge detection problem and produces a safe, reviewable deletion plan. Use at sprint boundaries or whenever branch sprawl accumulates.
argument-hint: "[--apply | --report-only | --stale-days <N>]"
allowed-tools: Bash(gh *) Bash(git *) Bash(jq *) Bash(sort *) Bash(awk *) Bash(grep *) Bash(date *) Bash(python3 *) Bash(sed *) Bash(mv *) Bash(cat *) Bash(xargs *) Bash(echo *) Bash(wc *) Read Write TodoWrite
---

# Branch Cleanup: Safe, Systematic Remote Branch Pruning

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Remove stale remote branches from `$CONFIG.repo` after auditing each against GitHub PR state.

---

## Repository Constant

```
REPO        = $CONFIG.repo
PROTECTED   = master
STALE_DAYS  = 30  (default; override with --stale-days <N>)
```

---

## Invocation Modes

### Mode 1: Report Only (default / safe)
```
/branch-cleanup
/branch-cleanup --report-only
```
Fetch all remote branches, categorize each, and print a report. Do NOT delete anything. Ask before proceeding.

### Mode 2: Apply
```
/branch-cleanup --apply
```
Run the full audit, then delete all branches confirmed safe (categories A + B below). Print each deletion. Skip any branch with an open PR.

### Mode 3: Custom stale threshold
```
/branch-cleanup --stale-days 60
```
Mark branches with no commits in the last 60 days as stale instead of the default 30.

---

## Why `git --merged` Is Not Enough

GitHub squash-merge and rebase-merge re-SHA commits, so `git branch -r --merged origin/master` misses most merged feature branches. The correct approach is to cross-reference the **GitHub PR state** for every branch.

---

## Step-by-Step Procedure

### Step 1 — Fetch & Sync

```bash
git fetch --prune origin
```

This removes any remote-tracking refs that no longer exist on GitHub and refreshes all branch pointers.

### Step 2 — Build Candidate List

Collect every remote branch except protected ones:

```bash
git branch -r \
  | grep -v ' -> ' \
  | grep -vE '^  origin/(HEAD|main)$' \
  | sed 's|  origin/||' \
  | sort > /tmp/fw_branches_all.txt
```

Note the **currently checked-out branch** and remove it from the candidate list:
```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
grep -vxF "$CURRENT_BRANCH" /tmp/fw_branches_all.txt > /tmp/fw_branches_candidates.txt
mv /tmp/fw_branches_candidates.txt /tmp/fw_branches_all.txt
```

### Step 3 — Fetch GitHub PR State for All Branches

Pull every PR (all states) with pagination to avoid per-branch API calls and to
ensure older PRs are not missed in repos with more than 500 PRs. Include
merge/close/update timestamps so later reporting can show merged or closed dates:

```bash
gh api --paginate \
  -H "Accept: application/vnd.github+json" \
  "/repos/$CONFIG.repo/pulls?state=all&per_page=100" \
  | jq -s 'add | map({
      number,
      title,
      headRefName: .head.ref,
      state: (if .merged_at != null then "MERGED" else (.state | ascii_upcase) end),
      mergedAt: .merged_at,
      closedAt: .closed_at,
      updatedAt: .updated_at
    })' \
  > /tmp/fw_all_prs.json
```

### Step 4 — Categorize Each Branch

For each branch in `/tmp/fw_branches_all.txt`:

| Category | Condition | Action |
|----------|-----------|--------|
| **A – Merged PR** | Branch has a PR with `state = MERGED` | **Safe to delete** |
| **B – Closed PR (abandoned)** | Branch has a PR with `state = CLOSED` | **Safe to delete** — treat closed PR branches as abandoned; review the Step 5 report before confirming so any WIP can be caught at that stage |
| **C – Open PR** | Branch has a PR with `state = OPEN` | **Keep — do not touch** |
| **D – No PR + stale** | No PR found AND last commit > STALE_DAYS days ago | **Flag for review** — ask user before deleting |
| **E – No PR + recent** | No PR found AND last commit ≤ STALE_DAYS days ago | **Keep — active work** |

Detect last commit age:
```bash
git log -1 --format='%ct' origin/<branch>
```
Compare against `$(date +%s) - (STALE_DAYS * 86400)`.

### Step 5 — Print the Report

Produce a report grouped by category:

```
========================================
 BRANCH CLEANUP REPORT — $(date +%Y-%m-%d)
========================================

SAFE TO DELETE (A — Merged PR): 34 branches
  feature/issue-508-ws-redis-reconnect    PR #551 merged 2026-04-13  (mergedAt: 2026-04-13)
  ...

SAFE TO DELETE (B — Closed/Abandoned PR): 1 branch
  alert-autofix-2                          PR #399 closed 2026-03-13

FLAG FOR REVIEW (D — No PR, stale >30d): 0 branches

KEEP (C — Open PR): 0 branches
KEEP (E — No PR, recent): 0 branches

Total deletable: 35
```

### Step 6 — Confirm (if --apply not passed)

Ask: "Delete 35 branches listed above? (yes/no)"

If no — exit.
If yes — proceed to Step 7.

### Step 7 — Delete

Before deleting, build `/tmp/fw_branches_safe.txt` from categories A and B (the confirmed-safe branches):
```bash
# Extract branch names for categories A (merged) and B (closed)
# OPEN always takes precedence: a branch with any OPEN PR is never safe to delete.
python3 - <<'EOF'
import json

branches = open('/tmp/fw_branches_all.txt').read().splitlines()
prs = json.loads(open('/tmp/fw_all_prs.json').read())

# Collect ALL PR states per branch (a branch may have multiple PRs)
# OPEN always takes precedence: a branch with any OPEN PR is never safe to delete.
pr_map: dict[str, set[str]] = {}
for p in prs:
    head_ref = p.get('headRefName')
    state = p.get('state')
    if not head_ref or not state:
        continue
    pr_map.setdefault(head_ref, set()).add(state)

safe = [
    b for b in branches
    if b in pr_map
    and 'OPEN' not in pr_map[b]
    and pr_map[b].intersection({'MERGED', 'CLOSED'})
]
with open('/tmp/fw_branches_safe.txt', 'w') as f:
    f.write('\n'.join(safe) + '\n' if safe else '')
print(f"{len(safe)} branches written to /tmp/fw_branches_safe.txt")
EOF
```

Then delete:
```bash
# Guard: skip if nothing to delete
if [ -s /tmp/fw_branches_safe.txt ]; then
  cat /tmp/fw_branches_safe.txt | xargs -n1 git push origin --delete
else
  echo "No safe branches to delete."
fi
```

Print each deleted branch.

### Step 8 — Prune Local Tracking Refs

```bash
git remote prune origin
```

### Step 9 — Verify

```bash
echo "Remaining remote branches:"
git branch -r | grep -v 'origin/HEAD'
```

---

## Post-Cleanup: Prevent Future Sprawl

### Option A — Enable GitHub Auto-Delete (Recommended)

After a PR merges, GitHub can automatically delete the source branch. Enable it once:

1. Go to `https://github.com/$CONFIG.repo/settings`
2. Scroll to **"Pull Requests"** section
3. Check **"Automatically delete head branches"**

With this on, only abandoned (never-PR'd) and long-lived branches will need manual cleanup.

### Option B — End-of-Sprint Habit

Add branch cleanup to the end-of-sprint checklist in `daily routine scripts/end_day.sh` or the sprint review process:

```bash
# At sprint close — dry run first
/branch-cleanup --report-only

# If report looks good
/branch-cleanup --apply
```

### Option C — Bot / CI Scheduled Cleanup (Advanced)

Add a GitHub Actions workflow that runs this script monthly and opens a PR with the deletion report:
```yaml
# .github/workflows/branch-cleanup.yml
on:
  schedule:
    - cron: '0 9 1 * *'  # First of every month
```

---

## Safety Guarantees

1. **Never deletes `master`** — hardcoded exclusion
2. **Never deletes current branch** — detected at runtime
3. **Never deletes branches with open PRs** — Category C check
4. **Dry run by default** — requires `--apply` or explicit yes to delete
5. **`git fetch --prune` first** — ensures list is current before any action

---

## Canonical References

- Git workflow rules: `docs/workflows/multi-agent-worktree-workflow.md`
- Merge and review workflow: `docs/workflows/merge-and-review-workflow.md`
- CLAUDE.md branch rules: `.claude/CLAUDE.md` (Parallel agent git workflow section)
- Sprint skill chain: `docs/workflows/sprint-skill-chain.md`

---

## On Complete

When branch cleanup is finished:

1. **Tell the user**: "{N} branches deleted. {M} remaining (with open PRs or recent activity)."
2. **Suggest next skill based on context**:
   - If this was end-of-sprint cleanup: "Branches cleaned. Run `/backlog-groom` to audit the open issue backlog for the next sprint cycle."
   - If this was ad-hoc cleanup: "Done. No further action needed."
3. **Pass forward**: No arguments needed for the next skill — `/backlog-groom` operates on the full backlog.
