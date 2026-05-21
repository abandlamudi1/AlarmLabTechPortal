---
name: guide-friction-sync
description: Sync open entries from $CONFIG.sprint.friction_file to GitHub issues on Project #55 (guide recommendations), creating one issue per friction entry and updating the entry's PR-target / status fields. Use at slice close or on demand to systematize what issue #52 describes manually.
argument-hint: "[--slice A] [--dry-run] [--no-pr] [--promote F<NN> <pr-url>]"
allowed-tools: Bash(gh *) Bash(git *) Bash(jq *) Bash(date *) Bash(grep *) Bash(sed *) Bash(cat *) Bash(echo *) Bash(sort *) Bash(tr *) Bash(head *) Bash(ls *) Read Write Edit Glob Grep
---

# Guide-Friction Sync — `$CONFIG.sprint.friction_file` → Project #55

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

## Why this skill exists

[docs/guide-friction.md](../../../docs/guide-friction.md) is the operational seam of the *"use AND improve the guides"* commitment in [docs/CLEANUP_PLAN.md](../../../docs/CLEANUP_PLAN.md). Agents and humans append friction entries (F01, F02, …) whenever a guide pattern is unclear, missing, or wrong. Per [CLEANUP_PLAN.md §Approach](../../../docs/CLEANUP_PLAN.md), at the end of each slice the **open entries are bundled into PRs against the corresponding guide repo**.

That bundling was previously manual (tracked as issue [#52](https://github.com/adc-quality/lab-tech-portal/issues/52)). This skill systematizes it:

1. **Discover** open friction entries.
2. **Mirror** each entry as a GitHub issue on the target guide's project board so cross-engagement visibility is preserved.
3. **Update** the friction entry in-place with the issue URL and new status.
4. **Refresh** the *Slice → PR target rollup* table at the bottom of `guide-friction.md`.

The skill does NOT open PRs against the guide repos — that step still requires human judgement on patch scope. It produces the tracking surface; the human (or a future companion skill) does the patch.

---

## Invocation modes

### Mode 1 — Sync all open entries (default)
```
/guide-friction-sync
```
Process every entry with `Status: open` (and no existing GitHub issue link in `PR target`).

### Mode 2 — Sync one slice
```
/guide-friction-sync --slice A
```
Only entries with `Slice: A` (matches the slice-id token).

### Mode 3 — Dry run
```
/guide-friction-sync --dry-run
```
Print the actions that would be taken; create no issues, edit no files.

### Mode 4 — Promote tracked → in-pr
```
/guide-friction-sync --promote F01 https://github.com/adc-quality/qe-architecture-ai-assisted-guide/pull/NN
```
Mark a specific friction entry as `in-pr` and pin the guide-repo PR URL. Use after the human has opened the actual guide-repo PR.

### Mode 5 — No-PR (used by /sprint-close)
```
/guide-friction-sync --no-pr
```
Run the full sync (Phases 0–4) but skip Phase 5's PR-open step. The `guide-friction.md` change rides on the caller's PR. Passed automatically when invoked from `/sprint-close`.

---

## Constants

```
LOCAL_FRICTION_LOG = $CONFIG.sprint.friction_file
PROJECT_OWNER      = adc-quality

# Each guide has its OWN project board. The Guide repo field in a friction entry
# routes the tracking issue to the matching project.
GUIDE_PROJECTS = {
  qe-architecture-ai-assisted-guide:           project_number=55, repo=adc-quality/qe-architecture-ai-assisted-guide,
  qe-repo-ai-assisted-guide:                   project_number=49, repo=adc-quality/qe-repo-ai-assisted-guide,
  qe-kubernetes-ai-assisted-deployment-guide:  project_number=43, repo=adc-quality/qe-kubernetes-ai-assisted-deployment-guide,
  QE-AI-Project-Organization:                  project_number=8,  repo=adc-quality/QE-AI-Project-Organization,
}

PROJECT_FIELDS_REQUIRED = {
  Pattern:     single-select,  # populated from the friction entry's Pattern / template / checker line
  Source Repo: single-select,  # populated from git config --get remote.origin.url at sync time
}
# Slice is NOT written to the project board (source-repo-local; stays in guide-friction.md only).
```

**Confirmed (2026-05-12):**
- **One issue per friction entry** — friction entries already enforce single-concern scope.
- **Each guide has its own project board** (#55 architecture, #49 qe-repo planner, #43 k8s, **#8 project-org**). The friction entry's `Guide repo` field routes the issue to the matching project.
- The tracking issue is created **in the guide repo itself** (e.g., `adc-quality/qe-architecture-ai-assisted-guide`) and then added to that guide's project board.
- **Project-board grouping is `Pattern` + `Source Repo`** — NOT `Slice`. Slice stays in the source repo's local `guide-friction.md` only.
- Skill **only opens issues, never PRs**. Humans (or a future companion skill) open guide-repo PRs when the fix is clear; the operator then runs `--promote F0X <pr-url>` to bump the local entry from `tracked` → `in-pr`.

---

## Phase 0 — Pre-flight

### Step 0.1 — Working tree must be clean

```bash
DIRTY=$(git status --porcelain)
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: Working tree has uncommitted changes. Commit or stash before running /guide-friction-sync."
  echo "$DIRTY"
  exit 1
fi
echo "Working tree clean."
```

### Step 0.2 — Confirm gh auth

```bash
gh auth status 2>&1
# Must show "Logged in to github.com" for the adc-quality org.
# If it shows an error or "not logged in", run: gh auth login
```

If `gh auth status` exits non-zero, stop with:
```
ERROR: gh auth is not valid. Run "gh auth login" and retry.
```

### Step 0.3 — Confirm each target project is visible

For each project number in GUIDE_PROJECTS (55, 49, 43, 8), verify visibility:

```bash
for PROJECT_NUM in 55 49 43 8; do
  gh project view "$PROJECT_NUM" --owner adc-quality --format json --jq '.title' 2>/dev/null \
    || echo "WARNING: Project #${PROJECT_NUM} not visible — entries routed there will be skipped."
done
```

A warning (not an error) is acceptable if a project is inaccessible — the skill proceeds for visible projects and surfaces skipped entries in the final summary.

### Step 0.4 — Resolve source repo short name

```bash
SOURCE_REPO_URL=$(git config --get remote.origin.url)
# Strip .git suffix and extract the repo slug (e.g. "lab-tech-portal")
SOURCE_REPO_SHORT=$(basename "$SOURCE_REPO_URL" .git)
SOURCE_REPO_FULL=$(echo "$SOURCE_REPO_URL" | sed 's|.*github.com[:/]\(.*\)\.git|\1|; s|.*github.com[:/]\(.*\)|\1|')
# e.g. "adc-quality/lab-tech-portal"
echo "Source repo: $SOURCE_REPO_FULL (short: $SOURCE_REPO_SHORT)"
```

### Step 0.5 — Determine default branch

```bash
DEFAULT_BRANCH=$(git remote show origin | grep 'HEAD branch' | awk '{print $NF}')
echo "Default branch: $DEFAULT_BRANCH"
```

---

## Phase 1 — Parse the friction log

Read `$CONFIG.sprint.friction_file` and extract each entry under `## Open friction entries`. Use the header regex `^### F(\d+) — (.+)$` to identify entries.

### Step 1.1 — Extract raw entry blocks

Use grep to find entry boundaries:

```bash
FRICTION_FILE="$CONFIG.sprint.friction_file"

# Get the line numbers of all entry headers
grep -n "^### F[0-9]\+ — " "$FRICTION_FILE"
```

For each entry, read the block from its header line to the line before the next `### F` header (or end of the section).

### Step 1.2 — Parse structured fields per entry

For each entry block, extract the following fields using grep:

```bash
# Given ENTRY_BLOCK (multi-line string for one F-entry):

ID=$(echo "$ENTRY_BLOCK" | grep -oP "^### F\K[0-9]+")
TITLE=$(echo "$ENTRY_BLOCK" | grep -oP "^### F[0-9]+ — \K.+")
DATE=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*Date:\*\* \K[0-9]{4}-[0-9]{2}-[0-9]{2}")
SLICE=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*Slice:\*\* \K\S+")
GUIDE_REPO=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*Guide repo:\*\* \`\K[^\`]+")
PATTERN=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*Pattern / template / checker:\*\* \K.+")
STATUS=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*Status:\*\* \`\K[^\`]+")
PR_TARGET=$(echo "$ENTRY_BLOCK" | grep -oP "\*\*PR target:\*\* \K.+")
```

If any required field (id, title, date, slice, guide_repo, pattern, status) is missing, skip that entry with:
```
WARNING: F{id} missing required field(s): {list}. Skipping.
```

### Step 1.3 — Apply mode filter

- If `--slice A` was passed: discard entries where `SLICE != "A"`.
- If status is `merged`, `resolved`, or `wont-fix`: discard (terminal states).
- Entries with status `tracked` or `in-pr`: keep for Phase 1.5 reconciliation.
- Entries with status `open`: keep for Phase 2 issue creation.

Build two lists:
- `RECONCILE_LIST`: entries with status `tracked` or `in-pr`
- `CREATE_LIST`: entries with status `open`

---

## Phase 1.5 — Reconciliation pass (self-correcting)

For every entry in `RECONCILE_LIST`:

### Step 1.5.1 — Resolve the tracking issue

Extract the issue URL from the entry's `PR target:` field. If the field is `<not yet>` or empty, move the entry to `CREATE_LIST` (it was tracked locally but the issue URL was lost).

```bash
ISSUE_URL="$PR_TARGET"
# e.g. https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/1
```

### Step 1.5.2 — Query the remote issue state

```bash
gh issue view "$ISSUE_URL" \
  --json state,closedAt,stateReason,timelineItems \
  --jq '{state: .state, stateReason: .stateReason, closedAt: .closedAt, events: [.timelineItems.nodes[] | select(.type == "CrossReferencedEvent" and .source.__typename == "PullRequest") | {pr_url: .source.url, pr_state: .source.state, pr_merged: .source.merged}]}'
```

If this returns a 404 / error:
```
WARNING: F{id}: issue URL {ISSUE_URL} returned 404. Entry may have been moved manually. Skipping reconciliation.
```

### Step 1.5.3 — Apply the transition table

Based on the observed remote state, update the local status:

| Observed remote state | Local `tracked` → | Local `in-pr` → |
|---|---|---|
| Issue OPEN, no linked PR events | (no change) | (no change) |
| Issue OPEN, has linked PR (open) | `in-pr` | (no change) |
| Issue CLOSED, stateReason = `completed`, linked PR merged | `merged` | `merged` |
| Issue CLOSED, stateReason = `completed`, no linked PR | `resolved` | `resolved` |
| Issue CLOSED, stateReason = `not_planned` | `wont-fix` | `wont-fix` |
| Issue not found (404) | warn + skip | warn + skip |

Record each transition in `RECONCILED_TRANSITIONS` for the final summary.

**Example transition output:**
```
F01: tracked → in-pr  (linked PR opened: https://github.com/adc-quality/qe-architecture-ai-assisted-guide/pull/7)
F02: in-pr → merged   (linked PR merged at sha abc1234)
```

---

## Phase 2 — Issue creation (routed by guide_repo)

For each entry in `CREATE_LIST`:

### Step 2.1 — Look up target project

```bash
GUIDE_REPO_KEY="$GUIDE_REPO"   # e.g. "qe-architecture-ai-assisted-guide"

case "$GUIDE_REPO_KEY" in
  qe-architecture-ai-assisted-guide)
    PROJECT_NUMBER=55
    TARGET_REPO="adc-quality/qe-architecture-ai-assisted-guide"
    ;;
  qe-repo-ai-assisted-guide)
    PROJECT_NUMBER=49
    TARGET_REPO="adc-quality/qe-repo-ai-assisted-guide"
    ;;
  qe-kubernetes-ai-assisted-deployment-guide)
    PROJECT_NUMBER=43
    TARGET_REPO="adc-quality/qe-kubernetes-ai-assisted-deployment-guide"
    ;;
  QE-AI-Project-Organization)
    PROJECT_NUMBER=8
    TARGET_REPO="adc-quality/QE-AI-Project-Organization"
    ;;
  *)
    echo "WARNING: F${ID}: unknown guide repo '${GUIDE_REPO_KEY}'. Skipping."
    continue
    ;;
esac
```

### Step 2.2 — Duplicate detection

Before creating an issue, search the target guide repo for an existing issue with a matching title prefix:

```bash
EXISTING=$(gh issue list \
  --repo "$TARGET_REPO" \
  --search "\"F${ID}\" in:title" \
  --state all \
  --json number,title,url \
  --jq '.[0]')

if [[ -n "$EXISTING" && "$EXISTING" != "null" ]]; then
  EXISTING_URL=$(echo "$EXISTING" | jq -r '.url')
  echo "F${ID}: already tracked at $EXISTING_URL — skipping create, updating local file only."
  # Update local status to 'tracked' with this URL
  continue
fi
```

### Step 2.3 — Derive pattern slug

From the entry's `Pattern / template / checker:` line:

```bash
PATTERN_VALUE="$PATTERN"

if echo "$PATTERN_VALUE" | grep -q "^docs/patterns/"; then
  # docs/patterns/<area>/<name>.md → <area>/<name>
  PATTERN_SLUG=$(echo "$PATTERN_VALUE" | sed 's|docs/patterns/||; s|\.md$||')
elif echo "$PATTERN_VALUE" | grep -q "^templates/"; then
  # templates/<dir>/<file>.template → <dir>
  PATTERN_SLUG=$(echo "$PATTERN_VALUE" | sed 's|templates/||; s|/.*||')
else
  # Verbatim (e.g. "qe-check", "qe-check-cicd")
  PATTERN_SLUG="$PATTERN_VALUE"
fi

echo "Pattern slug: $PATTERN_SLUG"
```

### Step 2.4 — Build the issue body

```bash
SOURCE_REPO_URL_WEB="https://github.com/$SOURCE_REPO_FULL"
FRICTION_LOG_ANCHOR=$(echo "f${ID}" | tr '[:upper:]' '[:lower:]')

ISSUE_BODY=$(cat <<EOF
**Source:** [$CONFIG.sprint.friction_file F${ID}](${SOURCE_REPO_URL_WEB}/blob/${DEFAULT_BRANCH}/$CONFIG.sprint.friction_file#${FRICTION_LOG_ANCHOR})
**Origin repo:** ${SOURCE_REPO_FULL}
**Source repo slice that surfaced this:** ${SLICE}  _(slice is origin-repo-local; see grouping note below)_
**Pattern / template / checker:** ${PATTERN}

## Friction
${FRICTION}

## Concrete impact in the originating repo
${IMPACT}

## Proposed guide change
${PROPOSAL}

---

_Generated by \`/guide-friction-sync\` from \`${SOURCE_REPO_FULL}\`. Update status in the originating repo's \`docs/guide-friction.md\` when this is resolved._
EOF
)
```

Issue title: `[F${ID}@${SOURCE_REPO_SHORT}] ${TITLE}`

Example: `[F01@lab-tech-portal] AGENTS.md.template needs a tool-by-tool coverage matrix section`

### Step 2.5 — Create labels on the target repo (if missing)

```bash
for LABEL in "guide-friction" "source:${SOURCE_REPO_SHORT}" "pattern:${PATTERN_SLUG}"; do
  gh label create "$LABEL" \
    --repo "$TARGET_REPO" \
    --color "0075ca" \
    --description "Auto-created by guide-friction-sync" \
    2>/dev/null || true   # ignore if label already exists
done
```

### Step 2.6 — Create the issue

```bash
ISSUE_URL=$(gh issue create \
  --repo "$TARGET_REPO" \
  --title "[F${ID}@${SOURCE_REPO_SHORT}] ${TITLE}" \
  --body "$ISSUE_BODY" \
  --label "guide-friction,source:${SOURCE_REPO_SHORT},pattern:${PATTERN_SLUG}" \
  --json url \
  --jq '.url')

echo "F${ID}: created issue at $ISSUE_URL"
```

If `--dry-run` is active, print what would be created and skip the `gh issue create` call.

### Step 2.7 — Add to project board

```bash
gh project item-add "$PROJECT_NUMBER" \
  --owner adc-quality \
  --url "$ISSUE_URL"

echo "F${ID}: added to Project #${PROJECT_NUMBER}"
```

### Step 2.8 — Populate project-board fields

#### Ensure `Pattern` and `Source Repo` fields exist (auto-create on first run)

```bash
# Check if Pattern field exists
PATTERN_FIELD_ID=$(gh project field-list "$PROJECT_NUMBER" \
  --owner adc-quality \
  --format json \
  --jq '.fields[] | select(.name == "Pattern") | .id' 2>/dev/null)

if [[ -z "$PATTERN_FIELD_ID" ]]; then
  echo "Creating Pattern field on Project #${PROJECT_NUMBER}..."
  gh project field-create "$PROJECT_NUMBER" \
    --owner adc-quality \
    --name "Pattern" \
    --data-type SINGLE_SELECT
  PATTERN_FIELD_ID=$(gh project field-list "$PROJECT_NUMBER" \
    --owner adc-quality \
    --format json \
    --jq '.fields[] | select(.name == "Pattern") | .id')
fi

# Repeat for Source Repo field
SOURCE_REPO_FIELD_ID=$(gh project field-list "$PROJECT_NUMBER" \
  --owner adc-quality \
  --format json \
  --jq '.fields[] | select(.name == "Source Repo") | .id' 2>/dev/null)

if [[ -z "$SOURCE_REPO_FIELD_ID" ]]; then
  echo "Creating Source Repo field on Project #${PROJECT_NUMBER}..."
  gh project field-create "$PROJECT_NUMBER" \
    --owner adc-quality \
    --name "Source Repo" \
    --data-type SINGLE_SELECT
  SOURCE_REPO_FIELD_ID=$(gh project field-list "$PROJECT_NUMBER" \
    --owner adc-quality \
    --format json \
    --jq '.fields[] | select(.name == "Source Repo") | .id')
fi
```

#### Set field values on the project item

```bash
# Get the project item ID for this issue
ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" \
  --owner adc-quality \
  --format json \
  --jq ".items[] | select(.content.url == \"$ISSUE_URL\") | .id" 2>/dev/null)

# Set Pattern field
if [[ -n "$ITEM_ID" && -n "$PATTERN_FIELD_ID" ]]; then
  gh project item-edit \
    --project-id "$(gh project view $PROJECT_NUMBER --owner adc-quality --format json --jq '.id')" \
    --id "$ITEM_ID" \
    --field-id "$PATTERN_FIELD_ID" \
    --text "$PATTERN_SLUG" 2>/dev/null || \
    echo "WARNING: Could not set Pattern field (may need to add option first). Set manually."

  gh project item-edit \
    --project-id "$(gh project view $PROJECT_NUMBER --owner adc-quality --format json --jq '.id')" \
    --id "$ITEM_ID" \
    --field-id "$SOURCE_REPO_FIELD_ID" \
    --text "$SOURCE_REPO_SHORT" 2>/dev/null || \
    echo "WARNING: Could not set Source Repo field. Set manually."
fi
```

Note: `gh project item-edit --text` sets a text value on single-select fields. If the option doesn't exist yet in the field definition, the API returns an error — the warning message guides the operator to add the option manually via the GitHub UI or `gh project field-option-add` (if that subcommand is available in the installed gh version).

---

## Phase 3 — Update the friction log in place

For each entry whose issue was just created (Phase 2) or whose status changed (Phase 1.5):

### Step 3.1 — Update `PR target` and `Status` fields

Use targeted edits on `$CONFIG.sprint.friction_file`. For each changed entry, replace the relevant lines:

```bash
# Update PR target line for F${ID}
Because the friction file uses consistent field prefixes, use the Edit tool (not sed) for precision:

- Find the exact line for `**PR target:**` in the entry block for F${ID}.
- Replace `<not yet>` (or stale URL) with the new issue URL.
- Find the `**Status:**` line and replace the backtick-quoted value with the new status.

After each edit, verify the change did not corrupt adjacent entries by checking that the next `### F` header is still present at the expected line number.

### Step 3.2 — Status vocabulary (6 values)

| Status | Meaning | Set by |
|---|---|---|
| `open` | Entry exists in `guide-friction.md`; no tracking issue yet | Author appends entry |
| `tracked` | Tracking issue exists on the target guide's project board; no PR | Phase 2 (skill) |
| `in-pr` | Guide-repo PR is open | Phase 1.5 (skill) or `--promote` (manual) |
| `merged` | Guide-repo PR was opened **and merged** — fix is in main | Phase 1.5 reconciliation |
| `resolved` | Tracking issue closed-as-completed **without** a PR (small direct fix or invalidation accepted by maintainer) | Phase 1.5 reconciliation |
| `wont-fix` | Tracking issue closed as `not_planned`, or entry retracted before tracking | Phase 1.5 reconciliation, or manual edit |

### Step 3.3 — Deposit the lifecycle diagram (idempotent)

On every run, check whether the lifecycle diagram already exists in `guide-friction.md`'s "How to use this file" section:

```bash
grep -q "author appends entry" "$FRICTION_FILE"
```

If the pattern is NOT found, insert the following diagram immediately after the `### Entry template` block (before `---`):

```markdown
### Status lifecycle

```
   author appends entry
            │
            ▼
        ┌───────┐
        │ open  │
        └───┬───┘
            │   /guide-friction-sync         (creates tracking issue)
            ▼
        ┌─────────┐
        │ tracked │ ◄─────────────────────┐
        └────┬────┘                       │
   PR opens  │                            │  (re-run keeps this fresh
   on guide  │                            │   via Phase 1.5 reconciliation)
   repo      ▼                            │
        ┌────────┐                        │
        │ in-pr  │                        │
        └────┬───┘                        │
   PR merges │       issue closed as      │
             │       completed w/o PR     │
             ▼              │             │
        ┌────────┐          │             │
        │ merged │          ▼             │
        └────────┘     ┌──────────┐       │
                       │ resolved │       │
                       └──────────┘       │
                                          │
        any state ─────► ┌──────────┐ ────┘
        (closed as       │ wont-fix │
         not_planned)    └──────────┘
```
```

If the pattern IS already found, skip this step (idempotent).

---

## Phase 4 — Refresh the rollup table

### Step 4.1 — Rebuild the Slice → PR target rollup

Read all entries (including terminal-status ones) from `guide-friction.md`. Group by `(slice, guide_repo)`. Exclude `wont-fix` entries from the Open column but keep them noted as retracted.

For each group, build a row:

```bash
# Pseudocode — implement as a Python or jq pipeline over the parsed entry JSON
for SLICE_KEY in sorted(unique slices):
  for GUIDE_REPO_KEY in sorted(unique guide_repos for this slice):
    ENTRIES = [entries where slice == SLICE_KEY and guide_repo == GUIDE_REPO_KEY]
    OPEN_ENTRIES = [e for e in ENTRIES if e.status not in (wont-fix, merged, resolved)]
    WONT_FIX = [e for e in ENTRIES if e.status == wont-fix]
    ENTRY_TEXT = ", ".join(
      "[F{id}]({pr_target}) {status}" if pr_target != "<not yet>" else "F{id} {status}"
      for e in OPEN_ENTRIES
    )
    if WONT_FIX:
      ENTRY_TEXT += " — " + ", ".join("F{id} retracted" for e in WONT_FIX)
    emit: "| {SLICE_KEY} | {GUIDE_REPO_KEY} | {ENTRY_TEXT} |"
```

### Step 4.2 — Replace the existing rollup table

Find the existing `## Slice → PR target rollup` section and replace it with the newly generated table. Use the Edit tool for precision — locate the section header, find its end (next `##` or EOF), and replace the entire block.

---

## Phase 5 — Commit, push, and open a PR (source-repo only)

> **Scope clarification:** Phase 5 acts on the **source repo** (e.g., lab-tech-portal), not on any guide repo. The only file changed locally is `$CONFIG.sprint.friction_file`. Guide-repo issues were created in Phase 2; nothing else is written to guide repos here.

### Step 5.1 — Determine branch strategy

```bash
CURRENT_BRANCH=$(git branch --show-current)
TODAY=$(date +%Y-%m-%d)

if [[ "$CURRENT_BRANCH" == "master" || "$CURRENT_BRANCH" == "main" ]]; then
  # On default branch: create a dedicated sync branch
  SYNC_BRANCH="chore/guide-friction-sync-${TODAY}"
  git checkout -b "$SYNC_BRANCH"
  echo "Created branch: $SYNC_BRANCH"
else
  # On a feature branch: commit on the current branch
  SYNC_BRANCH="$CURRENT_BRANCH"
  echo "Committing on existing branch: $SYNC_BRANCH"
fi
```

### Step 5.2 — Build commit message

```bash
# Count outcomes
N1=$(echo "$NEWLY_TRACKED" | wc -w | tr -d ' ')      # new issues created
N2=$(echo "$NEWLY_IN_PR" | wc -w | tr -d ' ')        # reconciled to in-pr
N3=$(echo "$NEWLY_MERGED" | wc -w | tr -d ' ')       # reconciled to merged
N4=$(echo "$NEWLY_RESOLVED" | wc -w | tr -d ' ')     # reconciled to resolved

COMMIT_MSG="$CONFIG.jira.prefix: docs(guide-friction): sync — tracked ${N1}, in-pr ${N2}, merged ${N3}, resolved ${N4}"

# Simplify if only one count is non-zero
if [[ "$N1" -gt 0 && "$N2" -eq 0 && "$N3" -eq 0 && "$N4" -eq 0 ]]; then
  LABELS=$(printf 'F%s,' $NEWLY_TRACKED | sed 's/,$//')
  COMMIT_MSG="$CONFIG.jira.prefix: docs(guide-friction): sync — tracked ${LABELS}"
fi
```

### Step 5.3 — Commit the guide-friction.md change

```bash
git add $CONFIG.sprint.friction_file
git commit -m "$COMMIT_MSG"
```

### Step 5.4 — Push

```bash
git push -u origin "$SYNC_BRANCH"
```

### Step 5.5 — Open a PR (unless --no-pr was passed)

If `--no-pr` was passed (e.g., invoked from `/sprint-close`): skip PR creation. The guide-friction.md change rides on the caller's PR. Print:
```
--no-pr flag set: skipping PR. guide-friction.md committed and pushed on branch ${SYNC_BRANCH}.
```

Otherwise, determine if an open PR already exists for this branch:

```bash
EXISTING_PR=$(gh pr list \
  --repo $CONFIG.repo \
  --head "$SYNC_BRANCH" \
  --state open \
  --json number,url \
  --jq '.[0]' 2>/dev/null)
```

If an open PR exists for this branch, add a comment linking the sync summary:

```bash
EXISTING_PR_NUMBER=$(echo "$EXISTING_PR" | jq -r '.number')
gh pr comment "$EXISTING_PR_NUMBER" \
  --repo $CONFIG.repo \
  --body "$(cat <<EOF
## /guide-friction-sync completed (${TODAY})

${SYNC_SUMMARY_TABLE}

guide-friction.md updated and pushed on this branch.
EOF
)"
```

If no open PR exists, open one:

```bash
gh pr create \
  --repo $CONFIG.repo \
  --title "$CONFIG.jira.prefix: docs(guide-friction): sync to guide project boards (${TODAY})" \
  --body "$(cat <<EOF
Automated sync of \`$CONFIG.sprint.friction_file\` to guide project boards via \`/guide-friction-sync\`.

## Newly tracked
${NEWLY_TRACKED_TABLE}

## Reconciled
${RECONCILED_TABLE}

## Skipped / errors
- Skipped (terminal status): ${K} entries
- Errors: ${E} entries

---
Generated by \`.claude/skills/guide-friction-sync/SKILL.md\`. Review the local file diff and merge when ready.
EOF
)"
```

The PR is **always opened for human review**; the skill does NOT auto-merge.

---

## Output summary

After a successful run, print:

```
=== /guide-friction-sync summary ===

Newly tracked (Phase 2 — issue created):
| F-id | Title | Source slice | Target guide | Project | Issue URL |
|------|-------|--------------|--------------|---------|-----------|
| F04  | …     | 0            | architecture | #55     | …/issues/N |

Reconciled (Phase 1.5 — remote state changed since last sync):
| F-id | Old status | New status | Reason |
|------|------------|------------|--------|
| F01  | tracked    | in-pr      | linked PR opened |
| F02  | in-pr      | merged     | linked PR merged at <sha> |

Skipped (terminal status — merged/resolved/wont-fix): K entries
Errors (parse/route/404): 0 entries
guide-friction.md updated, committed on branch <branch>, pushed.
Source-repo PR opened for review: <pr-url>   (or: "--no-pr: skipped")

Next:
- Review and merge the source-repo PR above
- Open a guide-repo PR for any `tracked` entry where the fix is clear
- Or just re-run /guide-friction-sync later — Phase 1.5 catches state changes automatically
```

---

## Edge cases

- **Malformed entry**: a friction entry missing a required field → skip with a warning, do not abort.
- **Duplicate detection**: before creating the issue, search the target guide repo for an existing issue whose title contains `[F{id}@{source_repo_short}]`. If found, treat as already tracked and only update the local file.
- **Cross-engagement entries**: if a future adopter uses this skill from a different repo, the `Source:` line in the issue body must capture the originating repo. Handles this via `git config --get remote.origin.url` rather than hardcoding `lab-tech-portal`.
- **Unknown guide repo**: if a friction entry's `Guide repo` doesn't match any key in `GUIDE_PROJECTS`, skip with a warning and surface it in the final summary so the operator can fix the entry or extend the constant.

---

## Reconciliation state-transition examples

The following examples document the three common state paths through Phase 1.5.

### Path 1: open → tracked (normal new entry)

1. F05 is appended to `guide-friction.md` with `Status: open` and `PR target: <not yet>`.
2. Operator runs `/guide-friction-sync`.
3. Phase 1 places F05 in `CREATE_LIST`.
4. Phase 2 creates the tracking issue, e.g., `https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/9`.
5. Phase 3 sets `PR target: https://...issues/9` and `Status: tracked`.
6. Next run: Phase 1.5 reconciles — issue is OPEN with no linked PR → no status change.

### Path 2: tracked → in-pr (human opened a guide-repo PR)

1. F05 has `Status: tracked`, `PR target: .../issues/9`.
2. A human opens `qe-architecture-ai-assisted-guide` PR #12 and links it to issue #9.
3. Operator runs `/guide-friction-sync` again.
4. Phase 1.5 queries issue #9: `state = OPEN`, timeline has a CrossReferencedEvent of type PullRequest with `merged = false`.
5. Phase 1.5 transitions F05: `tracked` → `in-pr`. Phase 3 writes the change.
6. Summary shows: `F05: tracked → in-pr (linked PR opened)`.

### Path 3: in-pr → merged (guide-repo PR merged)

1. F05 has `Status: in-pr`, `PR target: .../issues/9`.
2. Guide-repo PR #12 is merged.
3. Operator runs `/guide-friction-sync`.
4. Phase 1.5 queries issue #9: `state = CLOSED`, `stateReason = completed`, timeline has PR with `merged = true`.
5. Phase 1.5 transitions F05: `in-pr` → `merged`. Phase 3 writes the change.
6. F05 moves to `## Merged / resolved friction` section on next Phase 4 rollup rebuild.

---

## Smoke-test verification (what to verify before promoting to live)

The following steps document what a smoke test against F01 and F03 should verify. **Do NOT run this live** — it would make real API calls to GitHub and create tracking issues on the guide repo. Document results in the PR description.

### Smoke-test checklist (F01 and F03 — both target qe-architecture-ai-assisted-guide → Project #55)

**Pre-conditions:**
- [ ] Working tree is clean
- [ ] `gh auth status` is valid for adc-quality org
- [ ] `gh project view 55 --owner adc-quality` resolves (project is visible)
- [ ] F01 and F03 have `Status: open` in `$CONFIG.sprint.friction_file`

**Phase 0 verification:**
- [ ] Skill detects clean working tree and proceeds
- [ ] Auth check passes without interactive prompt
- [ ] All four project numbers (55, 49, 43, 8) visibility checked; at minimum #55 is accessible

**Phase 1 verification (parse):**
- [ ] F01 is parsed with all 9 required fields populated
- [ ] F03 is parsed with all 9 required fields populated
- [ ] F02 (status: `wont-fix`) and F04/F05 (status: `open`) are handled correctly:
  - F02: discarded (terminal status)
  - F04, F05: included in CREATE_LIST (status `open`)
- [ ] Both F01 and F03 appear in CREATE_LIST

**Phase 1.5 verification (reconciliation):**
- [ ] No entries in RECONCILE_LIST (all open at smoke-test time)
- [ ] Reconciliation pass exits with no transitions recorded

**Phase 2 verification (issue creation — in dry-run):**
- [ ] Issue title for F01: `[F01@lab-tech-portal] AGENTS.md.template needs a "tool-by-tool coverage matrix" section`
- [ ] Issue title for F03: `[F03@lab-tech-portal] Worktree/branching skills missing from the architecture guide`
- [ ] Issue body for F01 contains the correct `Source:` link to `$CONFIG.sprint.friction_file#f01`
- [ ] Issue body for F01 contains the `Friction`, `Concrete impact`, and `Proposed guide change` sections
- [ ] Pattern slug for F01 derived as `agents-md` (from `templates/agents-md/AGENTS.md.template`)
- [ ] Pattern slug for F03 derived as `workflows/multi-agent-worktree-workflow` (from `templates/workflows/multi-agent-worktree-workflow.md`)
- [ ] Labels list: `guide-friction`, `source:lab-tech-portal`, `pattern:agents-md` (for F01)
- [ ] Target project: #55 for both entries

**Phase 3 verification (file update — in dry-run):**
- [ ] F01 `PR target` line would be updated from `https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/1` to the newly-created issue URL (or to a duplicate-detected URL)
- [ ] F01 `Status` line would change from `open` to `tracked`
- [ ] F03 `PR target` line would be updated similarly
- [ ] F03 `Status` line would change from `open` to `tracked`
- [ ] Lifecycle diagram insertion check: if not present, diagram is added to "How to use this file"

**Phase 4 verification (rollup rebuild — in dry-run):**
- [ ] Rollup table row for `Slice 0 / qe-architecture-ai-assisted-guide` is rebuilt with F01 and F03 linked
- [ ] F02 is listed as retracted in that row

**Phase 5 verification (commit/PR — in dry-run):**
- [ ] Commit message would be: `$CONFIG.jira.prefix: docs(guide-friction): sync — tracked F01, F03`
- [ ] Branch would be `chore/guide-friction-sync-<TODAY>` (if run from master)
- [ ] PR title would be: `$CONFIG.jira.prefix: docs(guide-friction): sync to guide project boards (<TODAY>)`

---

## Related

- [docs/guide-friction.md](../../../docs/guide-friction.md) — the source log
- [docs/CLEANUP_PLAN.md](../../../docs/CLEANUP_PLAN.md) — the "use AND improve the guides" decision
- Guide project boards (routed by `Guide repo` field):
  - [Project #55 — qe-architecture-ai-assisted-guide](https://github.com/orgs/adc-quality/projects/55)
  - [Project #49 — qe-repo-ai-assisted-guide_planner](https://github.com/orgs/adc-quality/projects/49)
  - [Project #43 — qe-kubernetes-ai-assisted-deployment-guide](https://github.com/orgs/adc-quality/projects/43)
  - [Project #8 — QE-AI-Project-Organization](https://github.com/orgs/adc-quality/projects/8)
- Issue [#52](https://github.com/adc-quality/lab-tech-portal/issues/52) — the manual version this skill replaces
- [.claude/skills/sprint-close/SKILL.md](../sprint-close/SKILL.md) — invokes this skill on the final PR of a slice
