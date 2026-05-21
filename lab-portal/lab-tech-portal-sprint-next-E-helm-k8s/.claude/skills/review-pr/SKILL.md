---
name: review-pr
description: Triage Copilot review comments on a PR using the tiered-review workflow, fix valid issues, reply to each comment, and verify CI. Use when processing PR review feedback. Supports --round N and --auto flags.
argument-hint: "[pr-number] [--round N] [--auto]"
allowed-tools: Bash(gh *) Bash(git *) Bash(cd *) Bash(python *) Bash(./node_modules/.bin/tsc *) Bash(npx *) Read Edit Write Glob Grep Agent TodoWrite
---

# Review PR: Tiered Copilot Comment Triage

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

You are processing a PR in the `$CONFIG.repo` repository.

**The canonical process lives in [`docs/workflows/pr-review-tiered.md`](../../../docs/workflows/pr-review-tiered.md).** This skill is a Claude Code operational wrapper around that document. Read the workflow doc first if you have any ambiguity about classifications, reply templates, or the round-dependent action table.

---

## Arguments

Parse `$ARGUMENTS` as `<pr-number> [--round N] [--auto]`:

- **`<pr-number>`** (required): the PR number
- **`--round N`** (optional): explicit round number (1, 2, or 3+). If omitted, auto-detect via reply-count heuristic. Default when unclear: round 1.
- **`--auto`** (optional): skip the Phase 2 "present triage table and wait" confirmation. Also: if round ≥ 3, automatically chain into `/defer-pr-comments` at the end.

Examples:
```
/review-pr 679                      # Round 1, interactive
/review-pr 679 --round 2            # Round 2, interactive
/review-pr 679 --round 3 --auto     # Round 3, autonomous, auto-defers remainder
```

---

## Phase 0: Detect Round (if not explicit)

If `--round` is not passed:

```bash
PR_AUTHOR_LOGIN=$(gh pr view "$PR_NUMBER" \
  --repo $CONFIG.repo \
  --json author \
  --jq '.author.login')

REPLY_COUNT=$(gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments \
  --jq "[.[] | select(.in_reply_to_id != null) | select(.user.login == \"$PR_AUTHOR_LOGIN\")] | length")

if [[ $REPLY_COUNT -eq 0 ]]; then
  ROUND=1
elif [[ $REPLY_COUNT -lt 16 ]]; then
  ROUND=2
else
  ROUND=3
fi
```

Report the detected round to the user before proceeding.

---

## Phase 1: Gather Context

### 1a. PR metadata
```bash
gh pr view $PR_NUMBER --json title,body,headRefName,baseRefName,state,commits,files
```

### 1b. CI status
```bash
gh pr view $PR_NUMBER --json statusCheckRollup --jq '.statusCheckRollup[] | "\(.name): \(.conclusion // .status)"' | sort -u
```

### 1c. All inline review comments (multi-round aware)

Copilot posts a NEW review on each push — each round's inline comments are attached to a specific review ID and will NOT appear in the flat `/pulls/comments` API alone. Fetch all rounds:

```bash
# Step 1: Fetch flat comment list (needed for reply-thread detection)
FLAT_COMMENTS=$(gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments \
  --jq '.[] | {id: .id, path: .path, line: .line, body: .body, user: .user.login, in_reply_to_id: .in_reply_to_id}')

# Step 2: List all Copilot review IDs (one per push round)
COPILOT_REVIEW_IDS=$(gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/reviews \
  --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]") | .id][]')

# Step 3: For each Copilot review, fetch its inline comments
for REVIEW_ID in $COPILOT_REVIEW_IDS; do
  gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/reviews/$REVIEW_ID/comments \
    --jq '.[] | {id: .id, review_id: .pull_request_review_id, path: .path, line: .line, body: .body, user: .user.login, in_reply_to_id: .in_reply_to_id}'
done
# Union the above — these are ALL Copilot inline comments across all review rounds
```

### 1d. PR-level review summary
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/reviews --jq '.[] | {id: .id, state: .state, user: .user.login, body: .body}'
```

### 1e. Files changed
```bash
gh pr diff $PR_NUMBER --name-only
```

**Unresolved comments** = top-level Copilot comments (where `in_reply_to_id` is null, from any Copilot review round) that have **no reply** from the PR author. Detection:
- Collect all Copilot top-level comment IDs from Step 1c (all rounds, where `in_reply_to_id` is null)
- For each, check the flat comment list from Step 1c for entries where `in_reply_to_id == <that comment ID>` and `user.login == <pr-author-login>` (derive from `gh pr view --json author --jq '.author.login'` — do not hardcode)
- If no such reply exists → **unresolved**; if a reply exists → already handled, skip

Focus triage only on unresolved comments. Re-reviewing already-replied comments causes duplicate replies.

Read each changed file to understand the code being reviewed.

---

## Phase 2: Triage Each Comment

Classify every unresolved comment using the taxonomy in [`docs/workflows/pr-review-tiered.md`](../../../docs/workflows/pr-review-tiered.md#classification-taxonomy). Then apply the **round-dependent action table** from that doc to determine the disposition.

Summary (authoritative version is the workflow doc):

| Classification | Round 1 | Round 2 | Round 3+ |
|---|---|---|---|
| BUG / SECURITY / CI_BREAK | MUST FIX | MUST FIX | MUST FIX |
| ROBUSTNESS | FIX | FIX | DEFER |
| PERFORMANCE / TYPE_SAFETY / TEST_HYGIENE | FIX if clear | DEFER | DEFER |
| STYLE / VISUAL_POLISH | FIX if trivial | DEFER | DEFER |
| FALSE_POSITIVE | DISMISS | DISMISS | DISMISS |
| SCOPE | Acknowledge + issue | Acknowledge | Acknowledge |
| DUPLICATE | Note owning PR | Note owning PR | Note owning PR |

**Never-soften rules** (always MUST FIX regardless of round): Redis connection not in `finally`, bare `except:`, hardcoded credentials, broken migration chain, missing auth on mutation endpoints. See the workflow doc's "Rules that NEVER soften" section.

### Triage rules
- Read the ACTUAL source file, not just the diff hunk. Line numbers can be stale.
- Cross-reference with CLAUDE.md hard rules.
- Shared-file comments (incidental overlap from another concern area) → classify as SCOPE or DUPLICATE.

### Output the triage table

```
| # | Comment ID | File:Line | Classification | Round-N Action | Summary |
|---|------------|-----------|----------------|----------------|---------|
| 1 | 123456     | foo.py:42 | BUG            | FIX            | ...     |
```

**If `--auto` is NOT passed**: STOP HERE and present the triage table. Wait for confirmation before Phase 3.

**If `--auto` is passed**: proceed immediately to Phase 3.

---

## Phase 3: Fix Valid Issues

### 3a. Worktree setup (preferred over checkout)

```bash
cd $(git rev-parse --show-toplevel)
BRANCH=$(gh pr view $PR_NUMBER --json headRefName --jq '.headRefName')
git fetch origin "$BRANCH"

WORKTREE_PATH="../FW-review-r${ROUND}-${PR_NUMBER}"
if ! git worktree list | grep -q "$BRANCH"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH"
fi
cd "$WORKTREE_PATH"
```

Use an existing worktree for this branch if one is already present (e.g., the original feature-work worktree).

### 3b. Apply fixes

For each comment with action = FIX:
1. Read the file at the referenced location
2. Make the minimal correct fix
3. Update tests if the fix changes behavior
4. Keep fixes scoped — no unrelated refactors

For SCOPE items: create a GH issue via `/create-issue`. Note the issue number for the reply.

### 3c. Local validation

```bash
# Backend
cd backend && python -m mypy . --ignore-missing-imports 2>/dev/null; cd ..
cd backend && python -m pytest tests/ -x -q 2>/dev/null; cd ..

# Frontend
cd frontend && ./node_modules/.bin/tsc --noEmit 2>/dev/null; cd ..
cd frontend && npx vitest run --reporter=verbose 2>/dev/null; cd ..
```

### 3d. Commit

Round 1:
```
$CONFIG.jira.prefix: fix(review): address Copilot PR review comments on #$PR_NUMBER
```

Round 2+:
```
$CONFIG.jira.prefix: fix(review): address round-$ROUND Copilot comments on #$PR_NUMBER
```

---

## Phase 4: Reply to Every Comment

Use the reply templates from [`docs/workflows/pr-review-tiered.md`](../../../docs/workflows/pr-review-tiered.md#reply-templates):

**Fixed:**
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/<COMMENT_ID>/replies \
  --method POST \
  --field body="Fixed in <commit-sha> — <brief description>."
```

**False positive:**
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/<COMMENT_ID>/replies \
  --method POST \
  --field body="Reviewed — not applicable here because <reason>. No changes needed."
```

**Deferred (round 2+):**
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/<COMMENT_ID>/replies \
  --method POST \
  --field body="Non-blocking — deferring to a follow-up."
```
Use the exact phrase `Non-blocking — deferring to a follow-up.` so it's greppable.

**Scope:**
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/<COMMENT_ID>/replies \
  --method POST \
  --field body="Valid concern but out of scope for this PR. Tracked in #<issue-number>."
```

**Duplicate:**
```bash
gh api repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/<COMMENT_ID>/replies \
  --method POST \
  --field body="This file is shared across multiple PRs. Fix will be addressed in PR #<owning-pr>."
```

---

## Phase 5: Push & Verify CI

### 5a. Push
```bash
git push origin "$BRANCH"
```

### 5b. Check CI
```bash
gh pr checks $PR_NUMBER --repo $CONFIG.repo
```

### 5c. If CI fails
- Read failing job logs
- Fix the failure (new commit: `$CONFIG.jira.prefix: fix(ci): resolve test failure on #$PR_NUMBER`)
- Push, repeat until green

---

## Phase 6: Decide Next Step

### If round 1 or 2, CI green
```
PR #N review complete (round $ROUND).
{fixed} fixed, {deferred} deferred, {dismissed} dismissed.
CI is green. Ready to merge via GitHub UI.
After merge: run /sprint-close N.
```

### If round 3+, unresolved comments remain

**If `--auto` was passed**: chain directly into `/defer-pr-comments $PR_NUMBER --auto` to bulk-defer the remainder.

**If interactive**: recommend the next action:
```
PR #N round-3 review complete.
{fixed} blocking items fixed. {remaining} non-blocking comments remain.
Recommended next step: /defer-pr-comments $PR_NUMBER --auto
This will create a single tracking issue and reply to each remaining comment with the link.
```

### If CI is failing
```
CI failing on {check}. Fix the failure before merging.
```

---

## Phase 7: Worktree Cleanup (only if this skill created one)

If Phase 3a created a new worktree (it wasn't already present):
```bash
cd $(git rev-parse --show-toplevel)
git worktree remove "$WORKTREE_PATH"
```

Do **not** remove pre-existing worktrees you didn't create.

---

## Critical Rules

1. **Follow the workflow doc.** If this skill disagrees with [`docs/workflows/pr-review-tiered.md`](../../../docs/workflows/pr-review-tiered.md), the workflow doc wins.
2. **Never-soften rules are BUG/SECURITY regardless of round.** See the workflow doc.
3. **Read actual source files**, not just diff hunks.
4. **Every comment gets a reply.**
5. **Push to the PR's branch**, never a sibling.
6. **Never force-push, never push to main, never skip hooks.**
7. **Conventional commits** with `$CONFIG.jira.prefix:` prefix on PR titles.
8. **Shared files**: only fix if CORE to this PR.

---

## On Complete

Output a structured summary. Pass the PR number forward to `/sprint-close` after merge, or to `/defer-pr-comments --auto` if round 3+ with unresolved items.
