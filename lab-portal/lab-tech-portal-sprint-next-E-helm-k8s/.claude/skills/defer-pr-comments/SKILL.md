---
name: defer-pr-comments
description: Extract unresolved Copilot review comments from a PR into a single deferred tracking issue, add it to the project board, and reply to each comment with the issue URL. Use when closing out a PR without fixing every comment immediately. Supports --auto to skip confirmation pauses.
argument-hint: "[pr-number] [--auto]"
allowed-tools: Bash(gh *) Bash(git *) Bash(cat *) Bash(rm *) Bash(mkdir *) Bash(jq *)
---

# Defer PR Comments: Extract → Issue → Board → Reply

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

You are processing a PR in the `$CONFIG.repo` repository.

This skill is the **deferral escape hatch** described in [`docs/workflows/pr-review-tiered.md`](../../../docs/workflows/pr-review-tiered.md#the-deferral-escape-hatch). Use it when you reach round 3 of tiered review, or when round-2 deferrals exceed ~5 items and the PR is otherwise ready to merge.

## Arguments

Parse `$PR_NUMBER` as `<pr-number> [--auto]`:

- **`<pr-number>`** (required): the PR number
- **`--auto`** (optional): skip the Phase 2 "present triage table and wait" confirmation. Use this when chaining from `/review-pr --round 3 --auto`.

### Safe argument parsing (run FIRST)

`$PR_NUMBER` is a single whitespace-joined string (e.g. `"714 --auto"`). Interpolating it directly into `gh api` URLs, filenames, or PR titles will produce malformed values like `pulls/714 --auto/comments`. Parse it before use:

```bash
read -r PR_NUMBER REST <<< "$PR_NUMBER"
if [[ "$REST" == *"--auto"* ]]; then AUTO=true; else AUTO=false; fi
```

Use the parsed `$PR_NUMBER` (just the integer) in all `gh` commands, filenames, and titles below — never the raw unparsed `$ARGUMENTS` value. Use `$AUTO` to gate the Phase 2 confirmation pause.

Your job is to find every unresolved Copilot review comment, classify it, create a single tracking GitHub issue for the deferrable items, add it to the project board, and reply to each comment with the issue link.

---

## Phase 1: Fetch All PR Comments

```bash
gh api --paginate --slurp "repos/$CONFIG.repo/pulls/$PR_NUMBER/comments?per_page=100" \
  | jq 'add | sort_by(.created_at)'
```

### Identify unresolved comments

A comment is **unresolved** if ALL of the following are true:
1. It is a **top-level** Copilot comment — `in_reply_to_id` is `null` AND `user.login` is `copilot-pull-request-reviewer`
2. No reply exists from any user (i.e., no other comment in the response has `in_reply_to_id` equal to this comment's `id`)

Collect the `id`, `path`, `line`, and `body` of each unresolved comment.

---

## Phase 2: Classify Each Unresolved Comment

For each unresolved comment, classify it using this table:

| Classification | Meaning | Disposition |
|---|---|---|
| **BUG** | Real correctness issue (logic error, crash, data corruption, race condition) | **MUST FIX — stop and fix before deferring** |
| **SECURITY** | Security vulnerability (injection, auth bypass, credential exposure) | **MUST FIX — stop and fix before deferring** |
| **ROBUSTNESS** | Missing error handling, unguarded edge case, resource leak | DEFER (flag with ⚠️) |
| **PERFORMANCE** | Inefficiency, N+1 query, unnecessary allocation | DEFER |
| **TYPE_SAFETY** | Incorrect or overly broad types, missing overloads | DEFER |
| **TEST_HYGIENE** | Missing tests, stale docstrings, assertion gaps | DEFER |
| **STYLE** | Naming, formatting, comment wording, docstring mismatch | DEFER |
| **VISUAL_POLISH** | UI alignment, colour, spacing concerns | DEFER |

**STOP if any BUG or SECURITY items are found.** Fix them on the branch before proceeding.

Present the triage table:

```
| # | Comment ID | File:Line | Classification | Summary |
|---|------------|-----------|----------------|---------|
| 1 | 123456789  | foo.py:42 | ROBUSTNESS     | ...     |
```

**If `--auto` is NOT passed**: STOP after presenting the triage table. Wait for operator confirmation before Phase 3.

**If `--auto` is passed**: proceed immediately to Phase 3 without waiting. Used when chaining from `/review-pr --round 3 --auto`.

If no unresolved comments exist, report that and stop (regardless of `--auto`).

---

## Phase 3: Create the Tracking Issue

> **CRITICAL — shell quoting safety**: Issue bodies contain backticks, parentheses, brackets, and other special characters that break inline `--body "..."` arguments. You MUST write the body to a temp file and use `--body-file`. Clean up the temp file immediately after.

### 3a. Write the body to a temp file via heredoc

```bash
mkdir -p .scripts
body_file=".scripts/issue-pr-$PR_NUMBER-body.md"
pr_title="$(gh pr view "$PR_NUMBER" --repo $CONFIG.repo --json title --jq '.title')"
cat > "$body_file" << 'ISSUE_BODY'
## Context

Deferred from PR #__PR_NUMBER__ — __PR_TITLE__.
These items were identified by Copilot review but are not blocking merge.
Each comment has been replied to with a reference to this issue.

## Deferred Items

| # | Comment ID | File:Line | Classification | Summary |
|---|------------|-----------|----------------|---------|
| 1 | 123456789  | foo.py:42 | ROBUSTNESS     | ...     |

## Acceptance Criteria

- [ ] Item 1: [short description]
- [ ] Item 2: [short description]

ISSUE_BODY
issue_body="$(<"$body_file")"
issue_body="${issue_body//__PR_NUMBER__/$PR_NUMBER}"
issue_body="${issue_body//__PR_TITLE__/$pr_title}"
printf '%s' "$issue_body" > "$body_file"

## Files to Modify

- `path/to/file.py`

## Story Points

[XS=1 / S=2 / M=3 / L=5 based on total count and complexity]
ISSUE_BODY
```

### 3b. Create the issue

```bash
gh issue create \
  --repo $CONFIG.repo \
  --title "fix(scope): [summary of deferred items] (PR #$PR_NUMBER follow-ups)" \
  --label "backend,could have" \
  --body-file .scripts/issue-pr-$PR_NUMBER-body.md
```

Note the returned issue URL and number.

### 3c. Clean up immediately

```bash
rm .scripts/issue-pr-$PR_NUMBER-body.md
```

> Do not leave temp files in `.scripts/`. Always `rm` in the same command chain or immediately after.

---

## Phase 4: Add Issue to Project Board #$CONFIG.github.defer_project_number

### 4a. Get the item ID

```bash
gh api graphql -f query='
mutation {
  addProjectV2ItemById(input: {
    projectId: "$CONFIG.github.defer_project_id"
    contentId: "ISSUE_NODE_ID"
  }) { item { id } }
}'
```

Get the issue node ID first:
```bash
gh issue view ISSUE_NUMBER --repo $CONFIG.repo --json id --jq '.id'
```

Then add to the board using the node ID above.

### 4b. Set Priority = P3

```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "$CONFIG.github.defer_project_id"
    itemId: "ITEM_ID"
    fieldId: "$CONFIG.github.defer_priority_field_id"
    value: { singleSelectOptionId: "1477ce02" }
  }) { projectV2Item { id } }
}'
```

### 4c. Set Size (choose based on total deferred item count)

| Count | Size | Option ID |
|-------|------|-----------|
| 1–2   | XS   | `f0bd6d0e` |
| 3–5   | S    | `9da8b29c` |
| 6–10  | M    | `16c2eabd` |
| 11+   | L    | `a2b8c401` |

Field ID for Size: `$CONFIG.github.defer_size_field_id`

Keep these Size option IDs aligned with `.claude/skills/create-issue/SKILL.md` for Project Board #$CONFIG.github.defer_project_number before substituting `SIZE_OPTION_ID` in the mutation below.

```bash
gh api graphql -f query='
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "$CONFIG.github.defer_project_id"
    itemId: "ITEM_ID"
    fieldId: "$CONFIG.github.defer_size_field_id"
    value: { singleSelectOptionId: "SIZE_OPTION_ID" }
  }) { projectV2Item { id } }
}'
```

---

## Phase 5: Reply to Each Unresolved Comment

For each comment ID collected in Phase 1, post a reply:

```bash
gh api "repos/$CONFIG.repo/pulls/$PR_NUMBER/comments/COMMENT_ID/replies" \
  -X POST \
  -f body="Deferred to #ISSUE_NUMBER for follow-up: ISSUE_URL"
```

Loop over all unresolved comment IDs and confirm each reply ID is returned.

---

## Phase 6: Summary

Report the outcome:

```
PR #NNN defer complete:
- X unresolved comments identified
- Issue #NNN created: [title]
- Board: P3 / SIZE
- Replies posted: X/X
- PR is clear to merge
```
