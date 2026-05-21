---
name: create-pr
description: "Create a GitHub PR for the lab-tech-portal. Use when: opening a PR, submitting code for review, creating feature/hotfix branches. Enforces JIRA prefix requirement ($CONFIG.jira.prefix), PR title format, and pre-merge checklist validation."
argument-hint: "branch-name or --draft flag"
allowed-tools: Bash(gh *) Bash(git *) Read Write
---

# Create Pull Request (lab-tech-portal)

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

Enforces project-specific PR requirements and guides through the full merge workflow.

## When to Use

- Opening a new PR from a feature/hotfix branch
- Converting draft PRs to ready for review
- Validating PR requirements before submitting for merge
- Creating parallel-work PRs under the multi-agent workflow

## Quick Checklist

Before running this skill:

- [ ] Branch created with pattern: `feature/issue-NNN-desc` or `hotfix/NNN`
- [ ] All commits pushed: `git push -u origin <branch>`
- [ ] Issue number available (from GitHub issue or sprint plan)
- [ ] CI checks passing locally or on remote (run `docker compose up` if needed)
- [ ] Code follows existing patterns (read relevant docs in `docs/architecture/`)

## Procedure

### 1. Verify Branch and Commits

Ensure your feature branch exists and all work is committed:

```bash
git branch -v                    # Confirm you're on the right branch
git log origin/master..HEAD        # See commits pending merge
```

If commits not pushed yet:
```bash
git push -u origin <branch-name>
```

### 2. Gather PR Metadata

Collect the following before opening the PR:

| Item | Source | Example |
|------|--------|---------|
| **Issue Number** | GitHub issue or sprint plan | `571` |
| **Scope/Category** | PR concern (e.g., `feat`, `fix`, `chore`) | `feat(board)`, `fix(redis)` |
| **Short Description** | What this PR accomplishes | `Implement board workflow service` |
| **Draft?** | Is this a work-in-progress? | Yes/No |

### 3. Validate PR Title Format

**CRITICAL**: PR title MUST start with the JIRA prefix. Format:

```
$CONFIG.jira.prefix: <scope>: <description>
```

Examples:
- ✅ `$CONFIG.jira.prefix: feat(board): implement workflow service`
- ✅ `$CONFIG.jira.prefix: fix(redis): ensure connection cleanup in finally blocks`
- ✅ `$CONFIG.jira.prefix: chore(tests): expand board config coverage`
- ❌ `feature: implement workflow` (missing JIRA prefix)
- ❌ `[$CONFIG.jira.prefix] feat(board)` (wrong bracket style)

### 4. Use the Create-PR Skill (or Copilot's Built-in)

**Option A: Built-in Copilot PR Tool** (recommended for quick use)

1. Press `Ctrl+Shift+P` → search for `GitHub: Create Pull Request`
2. Or use the VS Code GitHub extension UI in the Source Control panel
3. Paste the properly formatted title when prompted
4. Add description pointing to the issue and referencing the scope

**Option B: Command Line (gh CLI)**

```bash
gh pr create \
  --title "$CONFIG.jira.prefix: feat(board): implement workflow service" \
  --body "Implements #123. See $CONFIG.sprint.plans_dir/B571_sprint_4.md for context." \
  --draft  # Omit if ready for review
```

### 5. Complete the PR Checklist

After creating the PR, GitHub will present `.github/pull_request_template.md` in the description.

**Required checks before asking for review:**

- [ ] **Scope**: PR covers one concern (e.g., "runtime fix" or "feature") — no mixing unrelated changes
- [ ] **Parallel workflow**: If using git worktrees, confirm no stray agent changes
- [ ] **CI green**: All backend-tests, frontend-tests, and type-check pass
- [ ] **Migration safety**: If migrations added, verify numbering doesn't collide with in-flight branches
- [ ] **Redis blocks**: If creating Redis connections, confirm every `.from_url()` has `.close()` in `finally`
- [ ] **No bare exceptions**: No bare `except:` clauses anywhere
- [ ] **No hardcoded credentials**: All secrets use `FW_` env var pattern

### 6. Request Review

Once checklist is complete:

1. Move PR from Draft to Ready (if created as draft)
2. Comment with the issue number: `Closes #123` or `Fixes #456`
3. Copilot review triggers automatically on PR create/update; otherwise request team review
4. Share link in sprint status or project board

### 7. Address Review Feedback (Tiered Workflow)

Follow [docs/workflows/pr-review-tiered.md](../../../docs/workflows/pr-review-tiered.md):

**Round 1** (first review):
- Fix: BUG, SECURITY, ROBUSTNESS, PERFORMANCE, TYPE_SAFETY
- Trivial STYLE fixes OK if under 2 min
- Push fixes to the same PR branch

**Round 2** (second review after Round 1 fixes):
- Fix: BUG, SECURITY, ROBUSTNESS only
- Defer: STYLE, PERFORMANCE, TYPE_SAFETY
- Push fixes to the same PR branch

**Round 3+** (if needed):
- Fix: BUG, SECURITY/CI_BREAK only
- For remaining items: Create a tracking issue, reply with the link, proceed to merge

### 8. Merge (Manual via GitHub UI)

Once all CI ✅ and review feedback addressed:

1. Go to PR page → click **Merge pull request**
2. Select merge strategy: **Squash and merge** (default for single concern)
3. Confirm commit message includes JIRA prefix: `$CONFIG.jira.prefix: feat(board): implement workflow service`
4. Click **Confirm merge**

GitHub will auto-delete the remote branch (check Settings → Pull Requests → "Automatically delete head branches").

### 9. Post-Merge Cleanup (for parallel work)

If you used git worktrees (`docs/workflows/multi-agent-worktree-workflow.md`):

```bash
# In the main worktree
git worktree remove ../lab-tech-portal-sprint-N-<concern>
```

Then use the `sprint-close` skill to close linked issues and update the project board.

## Common Issues

| Problem | Solution |
|---------|----------|
| "Title doesn't match required format" | Add `$CONFIG.jira.prefix: ` prefix and ensure `: ` separates scope from description |
| "CI failing on remote" | Run `docker compose up` locally, run `pytest backend/tests/`, then push fixes |
| "Migration numbering collision" | Check `ls backend/migrations/versions/ \| tail -1` on main and your branch; rebase if needed |
| "Redis connection not closed" | Search PR diff for `.from_url(` and ensure paired `.close()` in `finally` block |
| "Review feedback conflicts" | See tiered workflow — round 1 is broad, round 2 narrow, round 3+ defer to tracking issue |

## References

- **Pull request template**: [.github/pull_request_template.md](../../../.github/pull_request_template.md)
- **Tiered review workflow**: [docs/workflows/pr-review-tiered.md](../../../docs/workflows/pr-review-tiered.md)
- **Multi-agent worktree workflow**: [docs/workflows/multi-agent-worktree-workflow.md](../../../docs/workflows/multi-agent-worktree-workflow.md)
- **Git merge and review workflow**: [docs/workflows/merge-and-review-workflow.md](../../../docs/workflows/merge-and-review-workflow.md)
- **Redis connection best practices**: [docs/best-practices/redis-connections.md](../../../docs/best-practices/redis-connections.md)
- **Sprint close skill**: Use `/sprint-close` after merging to close linked issues and update project board
