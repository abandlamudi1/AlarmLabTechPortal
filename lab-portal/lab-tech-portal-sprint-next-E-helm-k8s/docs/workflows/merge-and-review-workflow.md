# Merge and Review Workflow

> Adapted from Video-FW-evaluation-process · genericized for any QE repo
> Canonical reference: https://github.com/adc-quality/Video-FW-evaluation-process/blob/f8fc8cea01708dc45495a3c5e26d09ac933df1ef/docs/workflows/merge-and-review-workflow.md

## The Problem

When two feature branches modify the same files and both target `main`, merging the first one invalidates the second. The longer branches live in parallel, the worse the conflict debt becomes:

| Duration apart | Typical pain level |
|---|---|
| < 1 day | Auto-merge usually works |
| 1–2 days | 2–5 conflict markers, manageable |
| 2+ days | 10+ conflicts, cherry-pick / rebase surgery needed |

## Pre-Branch Checklist

Run this **before** creating a new feature branch:

```bash
# 1. Is main up to date?
git fetch origin
git log --oneline main..origin/main  # should be empty

# 2. Any open PRs touching the same files I plan to modify?
gh pr list --state open --json number,title,headRefName --jq '.[] | "\(.number) \(.title)"'

# For each open PR, check file overlap:
comm -12 <(gh pr diff NNN --name-only | sort) <(echo "<your-planned-files>" | sort)
# If >30% overlap → merge that PR first, or branch FROM it

# 3. Migration number available (if applicable)?
ls <your-migrations-dir>/ | sort | tail -1
# If another branch has the next number, coordinate or use N+1
```

## During Development

### Rebase daily

```bash
git fetch origin
git rebase origin/main
# If conflicts: resolve, `git add`, `git rebase --continue`
```

Daily rebasing keeps conflict surface small. A 1-file conflict today is better than a 10-file conflict on Friday.

### Push review fixes to the right branch

When the reviewer (Copilot or equivalent) flags issues on PR #100:
- **Correct**: checkout PR #100's branch, fix, push to PR #100
- **Wrong**: fix on your current branch (PR #101), creating parallel implementations

This is the root cause of many conflict storms — review fixes meant for one PR ("the one being reviewed") get committed to a sibling branch ("the one currently checked out"), creating duplicate changes in two PRs that then conflict when both try to merge.

### Don't mix concerns in one PR

A PR should touch one concern area. Warning signs of scope creep:

| Concern | Example files |
|---|---|
| Backend infrastructure | `services/*`, `tasks/*`, integration clients |
| Frontend features | components, pages, hooks |
| CI/Docker | `Dockerfile`, `.github/workflows/*` |
| Admin bug fixes | admin endpoints, admin UI |

If your PR touches all four, split it. Each concern gets its own PR, merged in sequence.

## Merge Order Rules

### 1. Migration dependency chain (if applicable)
If PR A has migration `041` and PR B has migration `042` with `down_revision = '041'`, **A must merge first**. Alembic / your migration tool will fail otherwise.

```bash
grep "down_revision" <your-migrations-dir>/04*.py
```

### 2. Shared file priority
If two PRs both modify the same file:
- The PR closer to merge-ready (CI green, reviews done) goes first
- The other PR rebases after the first merges

### 3. Smaller first when equal priority
Smaller PRs are faster to review, less likely to have conflicts, and unblock the larger PR sooner.

## The Review-Fix-Merge Cycle

```
1. Push branch → CI runs → automated reviewer triggers
2. Triage review comments (see pr-review-tiered.md)
3. Fix valid issues, reply to every comment
4. Resolve all review threads
5. CI green → merge
6. Rebase dependent branches immediately
```

### Resolving review threads is a merge gate

GitHub branch protection typically requires all conversations resolved. After replying to each comment:

```bash
# Find unresolved threads
gh api graphql -f query='{
  repository(owner: "adc-quality", name: "lab-tech-portal") {
    pullRequest(number: NNN) {
      reviewThreads(first: 30) {
        nodes { id isResolved }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false) | .id'

# Resolve each
gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: "THREAD_ID"}) { thread { isResolved } } }'
```

## After Merge: Rebase Dependent Branches

Immediately after merging PR A, rebase any open branch that touches overlapping files:

```bash
git fetch origin
git checkout feature/dependent-branch
git rebase origin/main
# Resolve any conflicts
git push --force-with-lease origin feature/dependent-branch
```

Don't let rebases accumulate — each one makes the next harder.

## Conflict Resolution Strategies

### When rebasing gets painful (10+ conflicts)

Use the **cherry-pick strategy** instead of a blind rebase:

1. Identify which commits are already on main (merged via other PRs) — skip those
2. Create a new branch from current main
3. Cherry-pick only the commits that add NEW work
4. Resolve conflicts per cherry-pick (easier than resolving a mega-rebase)

### Common conflict patterns

| Pattern | Cause | Resolution |
|---|---|---|
| Same function modified differently | Parallel feature work | Keep main's version, manually apply your specific changes |
| add/add conflict | Both branches created the same file | Keep the more complete version |
| Import ordering | Linters reorder differently | Accept either, let linter fix |
| Migration number collision | Two branches created same revision | Renumber the later one |

## Anti-Patterns to Avoid

1. **Developing review fixes on a sibling branch** — creates duplicate work that conflicts on merge
2. **Letting branches sit for 3+ days without rebasing** — conflict debt compounds exponentially
3. **Mixing backend infra + frontend features + CI changes in one PR** — makes conflicts harder to resolve
4. **Force-pushing to a branch another developer is working on** — coordinate first
5. **Merging a dependent PR before its prerequisite** — breaks migration chains, causes runtime failures

## Related Docs

- [Multi-agent worktree workflow](multi-agent-worktree-workflow.md) — when to use worktrees vs single branches
- [Worktree lessons learned](worktree-lessons-learned.md) — per-issue vs per-concern grouping
- [PR tiered review](pr-review-tiered.md) — how to triage automated review comments
