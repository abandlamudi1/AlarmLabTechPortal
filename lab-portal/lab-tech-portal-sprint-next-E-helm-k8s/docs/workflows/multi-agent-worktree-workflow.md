# Multi-Agent Worktree Workflow

> Adapted from Video-FW-evaluation-process. Genericized for any QE repo.
> Canonical reference: https://github.com/adc-quality/Video-FW-evaluation-process/blob/f8fc8cea01708dc45495a3c5e26d09ac933df1ef/docs/workflows/multi-agent-worktree-workflow.md

## Problem Statement

When running multiple AI agent sessions in parallel (Claude Code, Copilot Chat, etc.), they cannot share the same IDE workspace because **git only allows one branch checked out at a time** in a working directory.

**Symptoms:**
- Agent A switches branches → affects Agent B's work
- Staged / unstaged changes from different issues get mixed together
- Merge conflicts between unrelated parallel work
- Cannot run independent test suites or Docker environments

## Solution: Git Worktrees

Git worktrees allow **multiple branches checked out simultaneously** in separate directories, all sharing the same `.git` database (efficient, no duplication).

> **Important:** Read [worktree-lessons-learned.md](worktree-lessons-learned.md) before deciding how many worktrees to create. The summary: **group by concern area, not per issue.**

---

## Workflow

### 1. Starting Work on a GitHub Issue

```bash
# Step 1: Ensure main is up to date in primary workspace
cd ~/dev/work/lab-tech-portal
git checkout main
git pull origin main

# Step 2: Create worktree for the concern area
# Format: ../lab-tech-portal-sprint-N-<concern>  (preferred — see lessons-learned)
#     or: ../lab-tech-portal-issue-NNN          (only for genuinely isolated work)
git worktree add ../lab-tech-portal-sprint-12-security -b feature/sprint-12-security

# Step 3: Open the worktree in a NEW IDE window
code --new-window ../lab-tech-portal-sprint-12-security
```

**Naming conventions:**
- **Concern-area branch** (preferred): `feature/sprint-N-<concern>` → worktree `../lab-tech-portal-sprint-N-<concern>`
- **Per-issue branch** (when truly isolated): `feature/issue-NNN-<short-desc>` → worktree `../lab-tech-portal-issue-NNN`
- **Bug branch**: `fix/issue-NNN-<short-desc>`
- **Hotfix branch**: `hotfix/issue-NNN-<short-desc>`

---

### 2. Opening Worktrees in VS Code (or your IDE)

#### The challenge
VS Code may try to reuse the same window when opening different worktrees from the same repository. This breaks isolation between parallel agent sessions.

#### Method 1: CLI with `--new-window` (recommended)
```bash
code --new-window ~/dev/work/lab-tech-portal-sprint-12-security
```

Why this works: `--new-window` forces a new window instance, never reusing existing ones.

**Pro tip — alias:**
```bash
# Add to ~/.zshrc or ~/.bashrc (or PowerShell profile)
alias code-new='code --new-window'
```

#### Method 2: File → New Window first
1. In current IDE: File → New Window (`Cmd+Shift+N` / `Ctrl+Shift+N`)
2. In the new empty window: File → Open Folder → navigate to the worktree

#### Method 3: File explorer right-click
- **macOS:** right-click folder in Finder → Open With → Visual Studio Code
- **Windows:** right-click folder in Explorer → Open with Code
- **Linux:** right-click folder in file manager → Open with Code

#### Method 4: IDE profiles (for frequent parallel work)
Create separate profiles per worktree so window state doesn't conflict.

#### Verify it worked

You should see two separate IDE windows with different branches checked out. In each terminal:

```bash
pwd                      # should show different paths
git branch --show-current # should show different branches
```

#### Troubleshooting

| Problem | Solution |
|---------|----------|
| IDE still opens in the same window | Close all windows; use `code --new-window` explicitly; disable "restore windows" in settings |
| Both windows show the same branch | You opened the same directory twice — verify `pwd` differs |

---

### 3. Working in the Worktree

Each worktree is completely independent:
- Has its own checked-out branch
- Has its own working directory changes
- Can run its own containers (with port remapping)
- Shares the same `.git` history and remotes

```bash
cd ~/dev/work/lab-tech-portal-sprint-12-security

# Normal git workflow
git status
git add .
git commit -m "feat(security): add CSRF protection"
git push -u origin feature/sprint-12-security

# Open PR
gh pr create --title "feat(security): sprint 12 security batch"
```

### 4. Managing Multiple Worktrees

```bash
git worktree list
```

Example output:
```
/Users/snodder/dev/work/lab-tech-portal                            abc1234 [main]
/Users/snodder/dev/work/lab-tech-portal-sprint-12-security         def5678 [feature/sprint-12-security]
/Users/snodder/dev/work/lab-tech-portal-sprint-12-data-integrity   9876fed [feature/sprint-12-data-integrity]
```

### 5. Cleaning Up After PR Merge

```bash
# In primary workspace
cd ~/dev/work/lab-tech-portal
git checkout main
git pull origin main

# Remove worktree
git worktree remove ../lab-tech-portal-sprint-12-security

# Delete feature branch (local + remote)
git branch -d feature/sprint-12-security
git push origin --delete feature/sprint-12-security
```

If the worktree has uncommitted changes, git will block removal. Commit/push first, or `--force` to lose changes (dangerous).

---

## Common Scenarios

### Scenario 1: Sprint batch (multiple related issues)
```bash
git worktree add ../lab-tech-portal-sprint-12-backend -b feature/sprint-12-backend
git worktree add ../lab-tech-portal-sprint-12-frontend -b feature/sprint-12-frontend
# 2 worktrees grouped by concern, not 10 worktrees per issue
```

### Scenario 2: Two agents working simultaneously
- **Agent A**: `feature/sprint-12-backend` in `~/dev/work/lab-tech-portal-sprint-12-backend`
- **Agent B**: `feature/sprint-12-frontend` in `~/dev/work/lab-tech-portal-sprint-12-frontend`

No conflicts as long as the concern areas have minimal file overlap.

### Scenario 3: Emergency hotfix during sprint
```bash
git worktree add ../lab-tech-portal-hotfix-500 -b hotfix/issue-500-critical
code --new-window ../lab-tech-portal-hotfix-500
```

### Scenario 4: Cleaning up after a sprint
```bash
git worktree list
git worktree remove ../lab-tech-portal-sprint-12-backend
git worktree remove ../lab-tech-portal-sprint-12-frontend
git worktree prune
```

---

## Directory Layout

```
~/dev/work/
├── lab-tech-portal/                            # Primary (main branch)
│   ├── .git/                                 # Shared git database
│   ├── src/
│   └── docs/
├── lab-tech-portal-sprint-12-backend/          # Worktree
└── lab-tech-portal-sprint-12-frontend/         # Worktree
```

All worktrees share the same `.git` directory in the primary workspace.

---

## Troubleshooting

### `fatal: 'xyz' is already checked out at '/path/to/worktree'`
Branch already checked out elsewhere. Use a different branch name or remove the existing worktree first.

### `fatal: '/path/to/worktree' already exists`
Directory exists, may be orphaned. Try `git worktree remove ../path` first, then `git worktree prune`. If the directory exists but is *not* in `git worktree list`, only then `rm -rf` it manually.

### `cannot remove worktrees with modifications`
Worktree has uncommitted changes. Commit/push first, or `git worktree remove --force` (loses changes).

### Container port conflicts between worktrees
Remap ports per worktree:
```bash
# Worktree 1: default ports
docker compose up

# Worktree 2: override
export BACKEND_PORT=8001 FRONTEND_PORT=3001 POSTGRES_PORT=5433 REDIS_PORT=6380
docker compose up
```

---

## Benefits

✅ True isolation — each agent works independently
✅ No branch switching conflicts — each worktree has its own branch checked out
✅ Parallel testing and Docker environments (with port remapping)
✅ Efficient — shares `.git` database, no repo duplication
✅ Clean history — each PR has focused commits

---

<a id="cross-platform-guide"></a>
<details>
<summary>🖥️ <strong>Cross-Platform Notes</strong> (Windows / macOS / Linux — click to expand)</summary>

All `git worktree` commands work identically on Windows, macOS, and Linux. The shell wrappers below assume bash/zsh; PowerShell users can run the same `git` commands directly.

| Bash | PowerShell |
|---|---|
| `cd ~/dev/work/repo` | `cd $HOME/dev/work/repo` |
| `git worktree add ../repo-issue-232 -b feature/...` | (same) |
| `code --new-window ../repo-issue-232` | (same) |
| `export VAR=value` | `$env:VAR = "value"` |
| `git worktree remove ../repo-issue-232` | (same) |

</details>

---

## References

- [Git Worktree docs](https://git-scm.com/docs/git-worktree)
- [Worktree lessons learned](worktree-lessons-learned.md) — read this for the "concern area vs per-issue" rule
- [Merge & review workflow](merge-and-review-workflow.md) — pre-branch checklist and merge sequencing
- [PR tiered review](pr-review-tiered.md) — review process per PR
