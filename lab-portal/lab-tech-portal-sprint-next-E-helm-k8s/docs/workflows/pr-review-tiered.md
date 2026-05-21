# PR Review — Tiered Workflow

> Adapted from Video-FW-evaluation-process · genericized for any QE repo
> Canonical reference: https://github.com/adc-quality/Video-FW-evaluation-process/blob/f8fc8cea01708dc45495a3c5e26d09ac933df1ef/docs/workflows/pr-review-tiered.md

**Canonical source of truth for the PR review process.** This document is LLM-agnostic and reviewer-agnostic. It applies whether review is performed by Claude Code, GitHub Copilot Chat, Cursor, ChatGPT, or a human.

---

## Why Tiered Review Exists

A single PR can receive 10–40 inline comments from an automated reviewer. On the first pass, most of them are worth addressing. On the second and third passes — after fixes are pushed — the reviewer tends to re-surface stylistic preferences and re-negotiate already-resolved debates. Treating round 3 comments with round 1 rigor stalls merges and frustrates reviewers without improving code quality.

The solution is a **graduated strictness model**: fix broadly in round 1, narrow in round 2, and defer nearly everything in round 3+ via the [deferral escape hatch](#the-deferral-escape-hatch).

---

## Definitions

### Round
One iteration of the review → fix → push → re-review cycle on a single PR.

| Round | Trigger |
|---|---|
| **1** | First automated review after PR opens (or after a major rewrite/rebase) |
| **2** | Second review after round 1 fixes are pushed |
| **3+** | Any subsequent review. Usually means stylistic disagreements persist. |

### Detecting the current round
Preferred (explicit): the operator passes `--round N` or the agent knows by context.

Fallback heuristic: count prior reply comments posted by the PR owner on this PR. A rough scale:
```bash
REPLY_COUNT=$(gh api repos/adc-quality/lab-tech-portal/pulls/<PR>/comments \
  --jq "[.[] | select(.in_reply_to_id != null) | select(.user.login == \"<owner>\")] | length")
# 0 → Round 1
# 1–15 → Round 2
# 16+ → Round 3+
```

This heuristic is imperfect — a chatty round 1 with many false-positive dismissals can inflate the count. Prefer explicit round numbers for rounds 2+.

---

## Classification Taxonomy

Every comment gets exactly one classification.

| Classification | Meaning |
|---|---|
| **BUG** | Real correctness issue — logic error, crash, data corruption, race condition |
| **SECURITY** | Security vulnerability — injection, auth bypass, credential exposure |
| **CI_BREAK** | The comment points at something already failing in CI |
| **ROBUSTNESS** | Missing error handling, unguarded edge case, resource leak |
| **PERFORMANCE** | Inefficiency, unnecessary allocation, N+1 query |
| **TYPE_SAFETY** | Incorrect or overly broad types, missing overloads |
| **TEST_HYGIENE** | Missing tests, stale docstrings, assertion gaps |
| **STYLE** | Naming, formatting, comment wording, docstring mismatch |
| **VISUAL_POLISH** | UI alignment, color, spacing |
| **FALSE_POSITIVE** | Comment is wrong — misreads the code or doesn't apply |
| **SCOPE** | Valid concern but outside this PR's scope |
| **DUPLICATE** | Same issue flagged on another PR due to shared files |

---

## Round-Dependent Action Table

The action column is the ONLY thing that changes across rounds. Classifications do not.

| Classification | Round 1 | Round 2 | Round 3+ |
|---|---|---|---|
| BUG | **MUST FIX** | **MUST FIX** | **MUST FIX** |
| SECURITY | **MUST FIX** | **MUST FIX** | **MUST FIX** |
| CI_BREAK | **MUST FIX** | **MUST FIX** | **MUST FIX** |
| ROBUSTNESS | FIX | FIX | DEFER |
| PERFORMANCE | FIX if clear win | DEFER | DEFER |
| TYPE_SAFETY | FIX if trivial | DEFER | DEFER |
| TEST_HYGIENE | FIX if in scope | DEFER | DEFER |
| STYLE | FIX if trivial (<2 min) | DISMISS/DEFER | DEFER |
| VISUAL_POLISH | FIX if trivial | DEFER | DEFER |
| FALSE_POSITIVE | DISMISS | DISMISS | DISMISS |
| SCOPE | Acknowledge + create issue | Acknowledge | Acknowledge |
| DUPLICATE | Note owning PR | Note owning PR | Note owning PR |

### Rules that NEVER soften across rounds

These rules are blocking regardless of round. If a comment identifies any of these, treat it as BUG/SECURITY:

- **Resource leaks** (DB connections, Redis connections, file handles) not closed properly
- **Bare `except:`** clauses (Python) or silent error swallowing (any language)
- **Hardcoded credentials** or secrets
- **Broken migration chain** (if using Alembic / similar — multiple heads, wrong `down_revision`)
- **Hardcoded URLs** to production systems
- **Missing auth checks** on endpoints that mutate state
- **N+1 queries** on request-path code (background tasks are lower priority)
- **Stale callers after a DB-layer attribute move**: when a PR moves a DB attribute to a new module (e.g. `tools.inventory.inventory_app.DB` → `tools.inventory.db.DB_PATH`), any file that still imports the old module name is a latent BUG — the `AttributeError` is masked because the code path containing the stale caller isn't exercised in the test run. On any PR that touches a `db.py` split, grep `app.py`, `conftest.py`, and service files for the old module alias before approving.

> Adapt this list to your repo. Add project-specific never-soften rules (e.g., "Redis connections in `finally`" for repos with that pattern).

---

## Reply Templates

Reply to **every single comment**. Silence reads as ignored feedback.

### Fixed
```
Fixed in <commit-sha> — <one-line description of the fix>.
```

### Dismissed as false positive
```
Reviewed — not applicable here because <reason>. No changes needed.
```

### Deferred (round 2+)
```
Non-blocking — deferring to a follow-up.
```

Reply body MUST begin with exactly `Non-blocking — deferring to a follow-up.` so the pattern is greppable across PRs. An optional second sentence may append a tracking issue reference, e.g. `Tracking issue: #<issue> (<issue-url>)`.

### Out of scope
```
Valid concern but out of scope for this PR. Tracked in #<issue> for follow-up.
```

### Duplicate (file shared with another PR)
```
This file is shared across multiple PRs. Fix will be addressed in PR #<owning-pr>.
```

---

## The Deferral Escape Hatch

When you reach round 3, OR when deferred items in round 2 exceed ~5, collapse the remaining unresolved comments into a single tracking issue:

1. **Stop fixing.** Push any blocking fixes (BUG/SECURITY/CI_BREAK) and commit.
2. **Bulk-defer** all remaining unresolved comments to a single GH issue:
   - Title: `fix(scope): [summary] (PR #<N> follow-ups)`
   - Label: `could have`
   - Add to Project Board #23 with Priority P3
   - Reply to every unresolved comment with: `Non-blocking — deferring to a follow-up. Tracking issue: #<issue> (<issue-url>)`
3. **Merge the PR.** The tracking issue captures the debt transparently.

This pattern is the release valve. Without it, a single PR can burn 3–4 review cycles on style preferences.

---

## The Full Review Loop

```
┌─────────────────────────────────────────────────────────────┐
│ 1. GATHER                                                   │
│    - PR metadata, CI status, all inline comments, reviews   │
│    - Read every changed file                                │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. DETECT ROUND                                             │
│    - Explicit (--round N) or heuristic (reply count)        │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. TRIAGE                                                   │
│    - Classify every comment                                 │
│    - Apply round-dependent action table                     │
│    - Output triage table; confirm before acting             │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. FIX (only FIX-marked items)                              │
│    - Work on the PR's branch in a worktree                  │
│    - Minimal scoped commits                                 │
│    - Run local validation (tsc, mypy, unit tests, etc.)     │
│    - Single commit: fix(review): address review comments    │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. REPLY                                                    │
│    - Every comment gets a reply using a template            │
│    - Fixed / Dismissed / Deferred / Scope / Duplicate       │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. PUSH & VERIFY CI                                         │
│    - Push to the PR's branch (never a sibling)              │
│    - Wait for CI, fix failures until green                  │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. DECIDE NEXT STEP                                         │
│    - Round 1 or 2, CI green → PR is ready for merge         │
│    - Round 3+ with unresolved style debate → run            │
│      deferral escape hatch                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Hard Rules (apply in every round)

1. **Never dismiss a BUG or SECURITY as false positive.** When in doubt, fix it.
2. **Never introduce new issues while fixing.** Keep fixes minimal.
3. **Read the actual source file** — comment line numbers can be stale.
4. **Every comment gets a reply.** No silent dismissals.
5. **Conventional commit format** on PR titles (e.g., `feat(scope): ...`, `fix(scope): ...`). This repo tracks issues in [GitHub Project #23](https://github.com/orgs/adc-quality/projects/23) — no JIRA prefix is required.
6. **Never force-push, never push to main, never skip hooks.**
7. **Push fixes to the PR being reviewed** — never to a sibling branch.
8. **Shared files** — only fix issues if the file is CORE to this PR. Otherwise classify as SCOPE or DUPLICATE.

---

## Tool-Specific Notes

### Claude Code users
Invoke `/review-pr <PR>` for round 1 (default). Pass `--round 2` or `--round 3` for later iterations. Pass `--auto` to skip the triage confirmation pause. Round 3 with `--auto` will chain into `/defer-pr-comments` automatically for remaining items.

### GitHub Copilot Chat / Cursor / ChatGPT users
Feed this document as context and ask the model to triage PR comments using the round-dependent action table above. Use `gh api repos/adc-quality/lab-tech-portal/pulls/<PR>/comments` to fetch comments. Post replies with `gh api .../replies -X POST -f body="..."`.

### Human reviewers
The same philosophy applies: on round 3, default to "non-blocking — defer" for any comment that isn't in the never-soften list. Merge velocity is a quality signal.

---

## Related Docs

- [`merge-and-review-workflow.md`](merge-and-review-workflow.md) — full merge sequence including branch hygiene
- [`multi-agent-worktree-workflow.md`](multi-agent-worktree-workflow.md) — worktree setup for parallel review sessions
- [`worktree-lessons-learned.md`](worktree-lessons-learned.md) — the cautionary case study behind the worktree rules
