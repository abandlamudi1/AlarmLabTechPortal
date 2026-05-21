# Worktree Strategy: Lessons Learned

> Original incident from Video-FW-evaluation-process · 2026-04-13
> Canonical reference: https://github.com/adc-quality/Video-FW-evaluation-process/blob/f8fc8cea01708dc45495a3c5e26d09ac933df1ef/docs/workflows/worktree-lessons-learned.md
>
> The issue numbers and PR references throughout this document refer to the original Video-FW-evaluation-process incident. They are preserved as concrete examples from a real audit; when adapting for your repo, the principle (group by concern area, not per issue) is what travels — the specific numbers won't match your project.
>
> Kept here as a cautionary case study. The rules in [`multi-agent-worktree-workflow.md`](multi-agent-worktree-workflow.md) are derived from these lessons.

## Context

Infrastructure audit sprint — 18 PRs from gap analysis, processed across 3 tiers.

## What We Tried

### Original approach: one worktree per GitHub issue

Created 18 parallel worktrees, one per issue, each with its own feature branch. All branches diverged from the same point on `main`. Each was pushed as a separate PR with automated review.

```
lab-tech-portal/                          (main)
lab-tech-portal-issue-508/                (ws-redis-reconnect)
lab-tech-portal-issue-509/                (sync-distributed-lock)
lab-tech-portal-issue-510/                (ws-jwt-auth)
... 15 more worktrees ...
```

### What went wrong

| Problem | Root cause | Impact |
|---------|-----------|--------|
| **50+ duplicate review comments** | 9 PRs shared ~14 identical monitoring/admin UI files | Same issues flagged in every PR |
| **Migration collisions** | 3 PRs all created revision `036` | Had to renumber to 037/038/039 manually |
| **Sequential merge bottleneck** | Strict "branch up-to-date with main" required for merge | Each merge invalidated every remaining PR (~5 min cycle per PR) |
| **Compound rebase conflicts** | Shared files diverged from main after each merge | Same import conflict resolved 8 times |
| **Cognitive overhead** | 18 worktrees on disk, 18 branches to track | Hard to remember which worktree had which fix |
| **Startup crash post-merge** | One PR refactored an API, another PR's code called the old method — never tested together | Backend crashed in prod |

### The core insight

These 18 issues weren't independent work streams. They came from a single infrastructure audit, touched overlapping files, and needed sequential migrations. **Worktree-per-issue is designed for parallel human developers working on unrelated features** — not for a single developer or AI agent processing a batch of related changes.

---

## What Works Better

### Worktree per concern area (not per issue)

Group related issues into a single branch / worktree based on which files they touch:

```
# Instead of 18 worktrees, use 3-4:
lab-tech-portal/                                    (main)
lab-tech-portal-sprint-data-integrity/              (issues #515, #516, #517, #518)
lab-tech-portal-sprint-security/                    (issues #510, #511, #528)
lab-tech-portal-sprint-monitoring/                  (issues #508, #509, #513, #521, #524, #527, #534, #561)
```

**Benefits:**
- Migrations are sequential within the branch (no numbering collisions)
- Shared files only appear in one PR (reviewed once)
- One rebase cycle per concern, not per issue
- Integration tested together (catches "PR A renames method, PR B calls old method")

### Decision matrix

| Scenario | Strategy | Worktrees |
|----------|----------|-----------|
| Sprint batch (10–15 related issues) | **1–3 worktrees by concern area** | `sprint-N-backend`, `sprint-N-frontend`, `sprint-N-infra` |
| Truly independent parallel work | **Per-issue worktrees** | Only when files genuinely don't overlap |
| Emergency hotfix during sprint | **Dedicated hotfix worktree** | `hotfix/issue-NNN` |
| Multi-agent parallel execution | **Per-agent worktree** | Agents assigned to non-overlapping concerns |

### How to assess overlap before creating worktrees

```bash
# For each proposed issue, list files it will likely touch.
# If >30% overlap between two issues, they belong in the same worktree.

# After PRs exist, you can verify with:
for pr in 544 545 546; do
  echo "=== PR #$pr ==="
  gh pr diff $pr --name-only
done | sort | uniq -c | sort -rn | head -10
# Files appearing in multiple PRs = shared files = should have been in one worktree
```

---

## What the Automated-Review Process Taught Us

The systematic review process ([`pr-review-tiered.md`](pr-review-tiered.md)) remains valuable regardless of worktree strategy:

1. **Triage before fix** — classify each comment (BUG/SECURITY/ROBUSTNESS/STYLE/FALSE_POSITIVE/SCOPE/DUPLICATE)
2. **Reply to every comment** — even false positives and duplicates get a response
3. **Resolve all threads** — branch protection typically requires this
4. **Sequential rebase-merge cycle** — strict status check policies usually require branch up-to-date with main

The review quality was excellent — 138 comments surfaced real bugs (savepoint flush ordering, unsafe concurrent refresh, stale lock release). The problem was the multiplier: reviewing the same shared-file issues 9x.

---

## Merge Order Strategy (still relevant)

When merging multiple PRs from a sprint batch, tier by isolation:

1. **Tier 1** (isolated, no shared files): merge first, in any order
2. **Tier 2** (moderate overlap): merge after Tier 1, may need light conflict resolution
3. **Tier 3** (heavy shared files): pick one "anchor" PR, fix shared issues there, merge first. Remaining PRs take main's version of shared files.

---

## Ruleset Requirements (typical for QE repos)

Most QE repos have rulesets that affect merge workflow:

| Rule | Impact |
|------|--------|
| `required_review_thread_resolution: true` | Must resolve ALL review threads before merge |
| `strict_required_status_checks_policy: true` | Branch must be up-to-date with main (rebase required after each merge) |
| `dismiss_stale_reviews_on_push: true` | Force-push triggers new review + may add new threads |
| `automated_code_review` (Copilot or equivalent) | Every push triggers re-review |

**Implication:** fewer PRs = fewer rebase-review-resolve cycles = faster shipping.

---

## Updated Rules

The conclusions of this case study are encoded in [`multi-agent-worktree-workflow.md`](multi-agent-worktree-workflow.md) and in your repo's `AGENTS.md`. The TL;DR:

1. **Group by concern area, not per issue** — default to 1–3 worktrees per sprint
2. **Check file overlap before splitting** — >30% overlap means same worktree
3. **Sequence migrations** — never create a migration with a number already in-flight on another branch
4. **Prefer fewer, larger PRs** when issues share files
5. **Integration-test grouped changes together** before merge

The bigger lesson: **parallelism is not free.** Coordinating 18 parallel work streams takes more total wall-clock time than serializing related work into 3 concern-area streams.
