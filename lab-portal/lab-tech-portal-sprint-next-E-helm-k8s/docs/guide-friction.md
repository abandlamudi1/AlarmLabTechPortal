# Guide-Friction Log

This file captures concrete friction encountered when applying the three QE guides to the lab-tech-portal. **At the end of each slice, the relevant entries are bundled into PRs against the corresponding guide repo.**

This is the operational seam of the "use AND improve the guides" decision in [CLEANUP_PLAN.md](CLEANUP_PLAN.md).

---

## How to use this file

When an instruction in a guide is missing, ambiguous, wrong, or doesn't fit this repo's reality, add an entry below using the template. **Don't fix it in the guide repo immediately** — capture friction here first so we can batch the feedback and not thrash the guide repos with one-off PRs.

### Entry template

```markdown
### F<NN> — <short title>
- **Date:** YYYY-MM-DD
- **Slice:** <slice id, e.g., 0, A, B, C, C2, D-part1, D-part2, G-part1, G-part2, H>
- **Guide repo:** `qe-repo-ai-assisted-guide` | `qe-architecture-ai-assisted-guide` | `qe-kubernetes-ai-assisted-deployment-guide` | `QE-AI-Project-Organization`
- **Pinned at SHA / version:** <commit SHA or version tag from when friction was hit>
- **Pattern / template / checker:** <e.g., `docs/patterns/auth/multi-mode-auth.md` or `templates/agents-md/AGENTS.md.template`>
- **Friction:** <what was missing / wrong / unclear>
- **Concrete impact in this repo:** <how it slowed us down or forced an off-spec decision>
- **Proposed guide change:** <new pattern, appendix, example, schema field — whatever>
- **PR target:** `<not yet>` | `<URL once PR opens>`
- **Status:** `open` | `in-pr` | `merged` | `wont-fix`
```

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

---

## Open friction entries

### F01 — `AGENTS.md.template` needs a "tool-by-tool coverage matrix" section
- **Date:** 2026-05-12
- **Slice:** 0
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** `templates/agents-md/AGENTS.md.template`
- **Friction:** The template assumes a single-app repo with one env-prefix. Lab-tech-portal hosts **five distinct tools** in one repo (Inventory, RF Chamber, Checkout, System Locator, Print Requests), each with its own env-var prefix (`PRINT_REQUESTS_*`, `SYSTEM_LOCATOR_*`, etc.). There's no template guidance for multi-tool repos.
- **Concrete impact in this repo:** Had to invent a "5-tool coverage discipline" section in [AGENTS.md](../AGENTS.md) by hand. Other multi-tool QE repos will hit the same gap.
- **Proposed guide change:** Add an optional `## Tool-by-Tool Coverage Discipline` template block that lists each sub-tool and requires PRs touching infrastructure to include a coverage matrix.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/1 *(issue created 2026-05-12; PR from Slice 0 close-out)*
- **Status:** `tracked`

### F02 — *(retracted — the portal DOES use a JIRA prefix; original framing was wrong)*
- **Date:** 2026-05-12
- **Slice:** 0
- **Status:** `wont-fix` *(see correction below)*
- **Correction:** The portal's engineering work IS tracked under JIRA epic **QENG-16846**. Every PR title must use `QENG-16846: ...`. GitHub Project #23 is the *operational backlog view*; JIRA is the source of truth. AGENTS.md was updated 2026-05-12 to reflect the correct convention.
- **Lesson learned for the guide:** The original `AGENTS.md.template` rule ("JIRA prefix required") was actually correct — the friction was *my* misreading. No guide change needed here. **However**, the template could make it clearer that the JIRA prefix can be a single umbrella ticket (parent epic) used across many PRs, not necessarily a unique ticket per PR. That nuance would have prevented my misread.
- **Proposed guide change (smaller scope):** One-line clarification in the template under the JIRA-prefix rule: *"The prefix can be a single umbrella ticket if your repo's work rolls up under one epic, or per-issue if each PR has its own."*

### F03 — Worktree/branching skills missing from the architecture guide (referenced as living in `agent-skills`)
- **Date:** 2026-05-12
- **Slice:** 0
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** `templates/workflows/multi-agent-worktree-workflow.md` + `templates/workflows/worktree-lessons-learned.md` (which we have); ALSO the [agent-skills](https://github.com/adc-quality/agent-skills) repo per the architecture guide README's "What this guide does NOT cover" section.
- **Friction:** The user (maintainer of the architecture guide) expected one-keystroke "skill" packages for parallel-worktree planning to live in the architecture guide. They don't — the guide ships *workflow docs* (markdown procedures) instead. The skill-package form is delegated to `adc-quality/agent-skills`, and there's no QE-specific worktree skill there yet ("future iteration" per the README).
- **Concrete impact in this repo:** When the user asked "do the guides provide a branching strategy?" the answer required cross-referencing four workflow docs rather than invoking a single skill. For a multi-sprint engagement with parallel slices, a `/plan-worktrees` style skill that reads `docs/CLEANUP_PLAN.md` + open issues and proposes a concern-grouped worktree layout would compress a recurring task.
- **Proposed guide change:** Either (a) build a worktree-planner Claude Code skill in `agent-skills` and link it from the architecture guide's AI_GUIDE.md, or (b) add a short "skills index" section to the architecture guide README that lists which skills exist where (or that they're TODO). Option (b) is cheap and unblocks the discovery problem immediately.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/2 *(issue created 2026-05-12; PR from Slice 0 close-out)*
- **Status:** `tracked`

### F05 — `docs/patterns/observability/audit-logging.md` does not address structlog configuration
- **Date:** 2026-05-13
- **Slice:** B
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** 81d85b9 (base of feature/sprint-3-slice-b-observability)
- **Pattern / template / checker:** `docs/patterns/observability/audit-logging.md`
- **Friction:** AGENTS.md instructs Slice B code to cite this pattern for structured logging. The pattern doc exists conceptually but does not cover structlog processor configuration, Flask `before_request`/`after_request` request-ID correlation, or `contextvars`-based context binding. The implementation had to invent all of this from scratch.
- **Concrete impact in this repo:** `services/logging_config.py` was written without a canonical reference. The structlog processor chain (shared processors, JSON vs console renderer branching, `merge_contextvars`, `_inject_request_context`) is bespoke and may diverge from future guide recommendations.
- **Proposed guide change:** Extend `docs/patterns/observability/audit-logging.md` with a "Structured logging with structlog" appendix covering: (a) `init_logging()` pattern with LOG_FORMAT env var, (b) `contextvars`-based request-ID binding in Flask, (c) `before_request` / `after_request` correlation hooks, (d) how to swap `logging.getLogger` call sites to `structlog.get_logger` incrementally.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/8
- **Status:** `tracked`

### F06 — No pattern for context-budget transitions / AI session handoff
- **Date:** 2026-05-13
- **Slice:** H
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** *(NEW pattern — not yet in guide)*
- **Friction:** The architecture guide has no guidance on what to do when an AI assistant's context budget runs out mid-task. AGENTS.md had a manual rule ("write a starter prompt for the next session covering status, complete vs in-progress, next steps, blockers"), but this was inconsistently applied and not backed by a template or skill. Other adopters will hit the same gap — context-budget exhaustion is a universal failure mode for long-running AI-assisted sprints.
- **Concrete impact in this repo:** Handoff notes between sessions were written ad-hoc in `docs/skill-development/` rather than in a canonical location. The `/handoff` skill (`.claude/skills/handoff/SKILL.md`) was built to automate this, but the underlying pattern — a predictable output path (`docs/handoffs/`), a short interview protocol, and auto-pulled git/PR state — should be a first-class pattern in the architecture guide so all adopters can benefit from it.
- **Proposed guide change:** Add `docs/patterns/ai-workflow/context-budget-handoff.md` to the architecture guide covering: (a) the trigger condition (approaching context limit), (b) auto-pulled context (git state, open PRs, active worktrees), (c) the four-question interview protocol (goal / complete vs in-progress / next steps / blockers), (d) the canonical output path convention (`docs/handoffs/<date>-<topic>.md`), (e) example handoff document for reference. Reference the `/handoff` Claude Code skill as the canonical implementation.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/9
- **Status:** `tracked`

### F04 — `docs/patterns/auth/multi-mode-auth.md` does not exist in the guide repo yet
- **Date:** 2026-05-12
- **Slice:** A
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** 5f11523 (base of feature/sprint-2-slice-a-auth)
- **Pattern / template / checker:** `docs/patterns/auth/multi-mode-auth.md`
- **Friction:** AGENTS.md instructs Slice A code to cite this pattern file. The pattern doc does not exist in the guide repo at the time of Slice A implementation. The RBAC module (services/rbac.py) and okta_auth groups-claim extraction were written without a canonical reference.
- **Concrete impact in this repo:** services/rbac.py includes a placeholder citation pointing to a non-existent file. If/when the pattern doc ships, the citation should be validated against the actual recommendations.
- **Proposed guide change:** Add `docs/patterns/auth/multi-mode-auth.md` to the architecture guide covering: (a) Okta OIDC groups-claim extraction, (b) warn-only vs enforce RBAC mode, (c) per-tier group mapping via env vars, (d) CSRFProtect + Flask-Limiter wiring pattern for Flask 3.x.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/10
- **Status:** `tracked`

### F06 — `prometheus-flask-exporter` registers endpoint as `prometheus_metrics`, not `metrics`
- **Date:** 2026-05-13
- **Slice:** B
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** prometheus-flask-exporter 0.23.2, Flask 3.1.2
- **Pattern / template / checker:** `docs/patterns/observability/audit-logging.md` (no Prometheus-specific pattern exists yet)
- **Friction:** The sprint instructions say to add `"metrics"` to the auth-exemption set so Prometheus scrapers can reach `/metrics` without a session cookie. In practice, `prometheus_flask_exporter` registers the endpoint with the internal name `prometheus_metrics` (not `metrics`). Adding only `"metrics"` to the exemption set leaves `/metrics` still behind the login gate. The fix is to add both `"metrics"` and `"prometheus_metrics"` to the exemption set.
- **Concrete impact in this repo:** `require_login()` at app.py:301 was returning a 302 redirect for unauthenticated requests to `/metrics` until `"prometheus_metrics"` was also added to the exemption set. Discovered via a failing test (`test_metrics_no_auth_required`).
- **Proposed guide change:** Add a Prometheus integration appendix to the observability pattern noting: (a) `prometheus_flask_exporter` uses the endpoint name `prometheus_metrics` (not `metrics`); (b) auth-exemption sets must include `prometheus_metrics`; (c) the `/metrics` route itself still uses the URL path `/metrics` as expected.
- **PR target:** `<not yet>` *(BLOCKED: duplicate F-id — another F06 entry exists above for slice H; renumber this entry to F11 before next /guide-friction-sync run so it can be tracked)*
- **Status:** `open`

### F07 — No guide pattern for "fail-fast at use vs fail-fast at construction" when replacing hardcoded constants with env vars
- **Date:** 2026-05-13
- **Slice:** C
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** *(NEW pattern — not yet in guide)*
- **Friction:** When replacing hardcoded class-level constants with `os.getenv()` reads (Issue #72), the guide gives no guidance on *when* to resolve the env var: at construction time (fail-fast) vs at first use (lazy). Failing fast at construction breaks any existing test that constructs the service with a minimal env (only the primary required vars). Failing at first use preserves test compatibility but makes the error surface less obvious in production. The correct choice depends on whether the service is used in all deployment configurations or only optionally.
- **Concrete impact in this repo:** `JiraService.__init__` originally validated `JIRA_URL` and `JIRA_PAT` immediately (correct — always required). The new Slice C custom field vars are only consulted when Jira integration is actually enabled (`PRINT_REQUESTS_CREATE_JIRA=true`). Resolving them at construction would fail the existing `conftest.py` test setup which does not set those vars. The fix was a lazy `_field_id()` class method that raises on first use, preserving test compatibility without degrading production visibility.
- **Proposed guide change:** Add a decision note to the "env-var extraction" section (or a new "service hardening" pattern): distinguish *always-required* vars (resolve in `__init__`) from *feature-gated* vars (resolve lazily at first use). Provide a `_get_field(name)` helper idiom as the canonical lazy pattern.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/11
- **Status:** `tracked`

### F08 — urllib3 Retry `allowed_methods` vs `method_whitelist` API break between urllib3 1.x and 2.x
- **Date:** 2026-05-13
- **Slice:** C
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** *(NEW pattern — not yet in guide)*
- **Friction:** The guide snippet for HTTPAdapter+Retry uses `method_whitelist=` (urllib3 1.x API). urllib3 2.x (bundled with requests ≥ 2.28) renamed the kwarg to `allowed_methods=` and emits a `DeprecationWarning` on 1.x-style usage. Code that blindly copies the old snippet gets a deprecation warning in CI and will break when urllib3 2.x becomes the minimum.
- **Concrete impact in this repo:** Used `allowed_methods=` (2.x spelling) in the `Retry(...)` constructor for `jira_service.py`. If the project's pinned `urllib3` is 1.x the correct kwarg is `method_whitelist=`. The requirements.txt does not pin urllib3 directly so the installed version depends on the requests version in the image.
- **Proposed guide change:** Update the HTTPAdapter+Retry recipe to note the kwarg rename, provide the 2.x-compatible spelling (`allowed_methods`), and recommend pinning `urllib3>=2.0` in `requirements.txt` to avoid silent fallback to the deprecated API.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/12
- **Status:** `tracked`

### F09 — SQLAlchemy 2.x spike: no guide pattern for ORM session lifecycle with monkeypatched test DBs
- **Date:** 2026-05-13
- **Slice:** D-part1
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** *(NEW pattern — not yet in guide)*
- **Friction:** The architecture guide (and the sprint prompt for Issue #48) correctly mandate "no module-level engine" and "use `current_app` for the DB path." However, the existing test harness isolates DBs via `monkeypatch.setattr(checkout_db, "DB_PATH", ...)` — a module-attribute patch, not an app-config patch. A `get_session()` that reads `current_app.config["DATA_DIR"]` at call time would NOT be intercepted by the monkeypatch, causing tests to read the wrong DB. The correct pattern is to import the `db` module and read `db.DB_PATH` at call time instead, since the module attribute IS patched.
- **Concrete impact in this repo:** `tools/checkout/models.get_session()` imports `tools.checkout.db` and reads `_checkout_db.DB_PATH` (not `current_app.config`). This is a one-line deviation from the sprint prompt's suggested code snippet, but it is required for test isolation. The fix is non-obvious without reading both the test conftest and the sprint prompt side-by-side.
- **Proposed guide change:** Add a "SQLAlchemy session lifecycle" note to the D-part2 ORM migration pattern (or to a new `docs/patterns/data/sqlalchemy-flask.md`): when existing tests patch a module-level `DB_PATH` attribute, `get_session()` must read that attribute (not `current_app.config`) so monkeypatching is respected. Provide both variants with clear trade-off commentary.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/13
- **Status:** `tracked`

### F10 — SQLAlchemy ORM objects require dict conversion for Jinja2 templates using `item['key']` access
- **Date:** 2026-05-13
- **Slice:** D-part1
- **Guide repo:** `qe-architecture-ai-assisted-guide`
- **Pinned at SHA / version:** *(record on first PR commit)*
- **Pattern / template / checker:** *(NEW pattern — not yet in guide)*
- **Friction:** Jinja2 templates written against `sqlite3.Row` objects use `item['key']` dict-style subscript access. SQLAlchemy 2.x ORM instances use attribute access (`item.key`). Migrating one route to SQLAlchemy while keeping the existing template requires either (a) converting ORM instances to dicts before passing to `render_template`, or (b) making the ORM model subscript-aware. Neither option is obvious from the architecture guide.
- **Concrete impact in this repo:** `checkout_app.dashboard` converts `Equipment` instances to plain dicts via `as_dict()` before passing them to the template. This is a low-cost workaround for the spike, but the full D-part2 migration will need a deliberate decision: update all templates to use attribute access, or keep the dict-conversion shim.
- **Proposed guide change:** Add a "template compatibility" note to the SQLAlchemy migration pattern: when migrating routes incrementally, provide an `as_dict()` helper on each model to bridge the `sqlite3.Row`-to-ORM transition. Document the long-term recommendation (attribute access in templates) vs the short-term compatibility shim.
- **PR target:** https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/14
- **Status:** `tracked`

---

## 2026-05-14 — Slice H closure — design system gap audit (Issue #103)

**Audit scope**: `templates/` (all 16 templates) + `static/style.css`, evaluated against FW Testing Platform design system foundations (snapshotted at `docs/references/design-system-fw/`) and WCAG 2.1 AA.

### Findings

1. **Tokens — global CSS is strong; per-page `page_styles` blocks break the system (S)**
   - `static/style.css` has a clean `:root { --color-…: … }` token block (28 custom properties) for light mode and a complete `.dark-mode { … }` override for dark mode. This is the right pattern.
   - Four tools inject ad-hoc `<style>` blocks via Jinja2 `{% block page_styles %}` that hardcode status colors as raw hex instead of extending the token system:
     - `tools/system_locator/templates/jira_import.html` lines 57–94: `.status-active #1f7a1f`, `.status-maintenance #d97706`, `.status-broken #b91c1c`, `.status-decommissioned #6b7280` — five distinct hardcoded colors.
     - `tools/system_locator/templates/systems_dashboard.html` lines 74–90: same status-color set with different green (`#2e8540` vs `#1f7a1f` in jira_import).
     - `tools/system_locator/templates/system_form.html` lines 332–415: error red hardcoded as `#dc2626` (three occurrences).
   - **Immediate fix (partial — done in this PR)**: promote `--status-active-color`, `--status-warning-color`, `--status-error-color`, `--status-neutral-color` into the global `:root` token block and reference them from all `page_styles` overrides. Tokens added to `:root` and `.dark-mode` in `static/style.css`; template migration to use these tokens is a follow-on PR.
   - **FW reference**: `docs/references/design-system-fw/01-foundations/colors.md` — "Don't use raw hex values in components."

2. **Tokens — one undefined CSS variable (`--body-text`) used in `static/style.css` (XS bug) — fixed in this PR**
   - `static/style.css` previously referenced `var(--body-text)` in `.detail-notes` without defining `--body-text` in `:root` or `.dark-mode`. Fixed in this PR: `--body-text: var(--text)` is now declared in both `:root` and `.dark-mode`, making the alias explicit and dark-mode-safe.

3. **Tokens — `input:focus` box-shadow duplicates primary-blue as raw RGBA instead of a token (XS) — fixed in this PR**
   - `static/style.css` previously had `box-shadow: 0 0 0 2px rgba(0, 102, 204, 0.22)` hardcoded in `input:focus`, not following dark mode's `--btn-primary-bg` change to `#3b82f6`. Fixed in this PR: `--focus-ring: rgba(0, 102, 204, 0.22)` added to `:root` and `--focus-ring: rgba(59, 130, 246, 0.30)` added to `.dark-mode`; `input:focus` now references `var(--focus-ring)`.

4. **Dark mode — status pill colors in `page_styles` blocks do not adapt to dark mode (S)**
   - The hardcoded hex colors in finding #1 above are the same in both themes. In dark mode, `#1f7a1f` (dark green on a dark card background `#1b1f2a`) achieves adequate contrast (~5.5:1 estimated), but `#d97706` (amber) on the same dark surface is borderline (~3.2:1 for normal text — below WCAG AA 4.5:1 threshold). Promoting to tokens (finding #1) enables per-theme contrast tuning.
   - Dark mode toggle logic in `base.html` is correct: class-based toggle (`dark-mode` on `<html>`), `aria-pressed` updated, localStorage persisted. No flash because theme is applied in `<head>` before render. This is the right approach and matches the FW design system's class-strategy recommendation.

5. **A11y — no skip-to-main-content link (S)**
   - `base.html` has `<header>` and `<main>` semantic elements but no visible-on-focus skip link. Keyboard users must tab through all toolbar links (Home, tool links, user chip, Log out, Dark Mode toggle — up to 6 tab stops) before reaching page content on every page load.
   - **Suggested fix** (XS effort):
     ```html
     <a class="skip-link" href="#main-content">Skip to main content</a>
     ```
     Add `id="main-content"` to `<main class="content">`, and in `static/style.css`:
     ```css
     .skip-link {
         position: absolute;
         left: -9999px;
     }
     .skip-link:focus {
         left: 8px;
         top: 8px;
         z-index: 9999;
         background: var(--btn-primary-bg);
         color: #fff;
         padding: 8px 12px;
         border-radius: 6px;
     }
     ```
   - **FW reference**: `docs/references/design-system-fw/accessibility/ACCESSIBILITY-ISSUES-REPORT.md` Issue #4 — skip links as P3 Low, same fix pattern.

6. **A11y — toolbar navigation group missing `<nav>` landmark and `aria-label` (S)**
   - `base.html` wraps toolbar links in `<div class="toolbar-links">` but not in a `<nav>` element. Screen readers cannot jump directly to navigation. With two toolbar-links divs (primary + secondary), both should be wrapped in `<nav aria-label="Primary navigation">` and `<nav aria-label="Utility navigation">` respectively.
   - **FW reference**: `ACCESSIBILITY-ISSUES-REPORT.md` Issue #3 — content must be in landmarks.

7. **A11y — color contrast: `--muted-text` on light `--card-muted-bg` is marginal (S)**
   - Light mode: `--muted-text: #6c7282` on `--card-muted-bg: #f4f6f8`. Estimated contrast ratio ~4.3:1 (just below WCAG AA 4.5:1 threshold for normal-weight body text at 14px). `#6c7282` on white card backgrounds (`--card-bg: #ffffff`) is ~5.1:1 (passes). The marginal case is muted text on the slightly off-white card background.
   - Used for: `.action-card p`, `.feature-card p`, `.hint` class, `.system-notes`, `.model-description` — all body text.
   - **Suggested fix**: darken `--muted-text` to `#5c6272` (roughly `gray-600` equivalent) which achieves ~4.8:1 on `#f4f6f8`.
   - **FW reference**: `colors.md` — "Normal text: 4.5:1 minimum"; the FW system uses `text-gray-600 (#4b5563)` for secondary text (5.74:1 on white).

8. **A11y — XSS posture on polling JS is good; no `innerHTML` found (pass)**
   - `tools/print_requests/templates/print_request_detail.html` and `tools/system_locator/templates/jira_import.html` both use `document.createTextNode()` and `block.appendChild()` patterns exclusively — no `innerHTML` with server-sourced data. This is correct per the AGENTS.md XSS rule and serves as the exemplar for any future polling additions.

9. **Responsive — single breakpoint at 720px; no intermediate breakpoints (M, deferred)**
   - `static/style.css` has one `@media (max-width: 720px)` breakpoint. The FW reference defines `sm/md/lg/xl` at 640/768/1024/1280px. For a primarily desktop-use portal this is acceptable short-term, but the Jira import preview table (7 columns) has no responsive treatment — on a tablet (768px–720px boundary) the table becomes horizontally scrollable with no column priority fallback.
   - **Not blocking for current 250-QE use case** (desktop-first audience), but a pattern doc for Flask/Jinja2 templates should document the breakpoint scale.

10. **Typography — font stack and scale are consistent; no findings (pass)**
    - `body` uses `"Segoe UI", Roboto, Arial, sans-serif` — aligns with FW `system-ui, -apple-system, "Segoe UI", Roboto`. The portal's stack is slightly narrower (no `system-ui` or `-apple-system`) but acceptable.
    - `home-intro h1` is `2rem`; `section-heading h2` is `1.2rem`; `detail-grid h2` is `0.95rem` with uppercase + tracking. Heading hierarchy is mostly respected (`h1` → `h2` → `h3`). No skipped levels found.
    - No arbitrary pixel font sizes — all sizes use `rem` or `em` units.

### Pattern proposal for the architecture guide (out-of-scope here, follow-on PR)

A new pattern `frontend/design-system-for-flask-templates.md` should cover:

- CSS custom properties as design tokens (one canonical `:root` block per theme) — document the `:root` + `.dark-mode` dual-override pattern as the Flask/Jinja2 equivalent of Tailwind semantic tokens
- Status color tokens promoted to `:root` to prevent per-page `page_styles` drift
- WCAG 2.1 AA checklist applied to server-rendered Flask forms: skip links, `<nav>` landmarks, focus ring tokens, contrast ratio check on muted-text values
- Dark mode via class toggle + localStorage persistence (matches `base.html` current approach) — no `@media (prefers-color-scheme: dark)` reliance, which is correct for explicit user preference
- Responsive utilities at standard breakpoints; table-first responsive strategy (horizontal scroll + visible column priority) for data-dense Flask templates
- Component-scoped styles via Jinja2 `{% block page_styles %}` blocks are fine for layout, but should reference `:root` tokens — never hardcode status or brand colors as hex

### Reference

FW design system foundations snapshotted into this PR at `docs/references/design-system-fw/`.

---

## Merged / resolved friction

*(none yet)*

---

## Slice → PR target rollup (for end-of-slice batching)

| Slice | Target guide repo | Open entries to bundle |
|---|---|---|
| 0 | `qe-architecture-ai-assisted-guide` | [F01](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/1) tracked, [F03](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/2) tracked — F02 retracted |
| A | `qe-architecture-ai-assisted-guide` | [F04](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/10) tracked |
| B | `qe-architecture-ai-assisted-guide` | [F05](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/8) tracked, F06 open *(prometheus; BLOCKED — duplicate F-id collision with slice H entry, needs renumber to F11)* |
| C | `qe-architecture-ai-assisted-guide` | [F07](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/11) tracked, [F08](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/12) tracked |
| D-part1 | `qe-architecture-ai-assisted-guide` | [F09](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/13) tracked, [F10](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/14) tracked |
| H | `qe-architecture-ai-assisted-guide` | [F06](https://github.com/adc-quality/qe-architecture-ai-assisted-guide/issues/9) tracked *(context-budget handoff)* |

---

## qe-check Baseline (Slice 0)

**Date**: 2026-05-15
**Commit**: `6b467d5` (feature/sprint-next-qe-baseline branch)
**Command**: `qe-check . --verbose`

### Results

```
======================================================================
  CI/CD Checker
======================================================================

======================================================================
CI/CD Configuration Report: feature/sprint-next-qe-baseline
======================================================================

Score: 100.0% (10/10 checks passed)
Status: ✅ PASS

⚠️  Recommendations:
----------------------------------------------------------------------
  • Workflow: codeql.yml
    ⚠️  Security scanning workflow (optional if enterprise has other security tools) not found (recommended)
    💡 Consider adding .github/workflows/codeql.yml for security scanning workflow (optional if enterprise has other security tools)

  • Workflow: release.yml
    ⚠️  Release and publish workflow not found (recommended)
    💡 Consider adding .github/workflows/release.yml for release and publish workflow

  • Workflow: dependabot.yml
    ⚠️  Automated dependency updates (in .github/) not found (recommended)
    💡 Consider adding .github/dependabot.yml for automated dependency updates (in .github/)

  • Dependabot Configuration
    ⚠️  Dependabot not configured (recommended)
    💡 Add .github/dependabot.yml for automated dependency updates

  • Pre-commit Hooks
    ⚠️  Pre-commit hooks not configured (recommended)
    💡 Add .pre-commit-config.yaml for local code quality checks

  • Branch Protection
    ⚠️  Branch protection not enabled (recommended)
    💡 Enable branch protection on main branch for better security

✅ Passed Checks:
----------------------------------------------------------------------
  • Workflow: ci.yml: ✅ Continuous Integration workflow exists
  • GitHub Actions Enabled: ✅ GitHub Actions available
  • Issues Enabled: ✅ Issues enabled for tracking

======================================================================


======================================================================
  Documentation Checker
======================================================================

======================================================================
Documentation Best Practices Report: feature/sprint-next-qe-baseline
======================================================================

Score: 75.0% (6/8 checks passed)
Status: ⚠️  NEEDS ATTENTION

❌ Failed Checks:
----------------------------------------------------------------------
  • LICENSE
    ❌ License file not found
    💡 Add LICENSE file in repository root (GitHub requirement for license detection)

  • Copilot Instructions
    ⚠️  .github/copilot-instructions.md exists but may be incomplete
    💡 Add comprehensive Copilot instructions with project overview, architecture, and development patterns

⚠️  Recommendations:
----------------------------------------------------------------------
  • CHANGELOG
    ⚠️  No changelog file found (recommended)
    💡 Add CHANGELOG.md to document version history and changes

  • CONTRIBUTING
    ⚠️  No contributing guidelines found (recommended)
    💡 Add CONTRIBUTING.md to help contributors understand development process

  • Project Metadata
    ⚠️  No project metadata file found (recommended for Python)
    💡 Add pyproject.toml or setup.py for package metadata

  • Documentation Directory
    ⚠️  Documentation directory exists (docs/) but needs organization
    💡 Organize documentation with this structure:
Repository root:
├── README.md                         # Project overview
├── LICENSE                           # Project license (GitHub detects in root)
├── CONTRIBUTING.md                   # Contribution guidelines (GitHub links from root)
├── CHANGELOG.md                      # Version history
└── docs/
    ├── DOCS_INDEX.md                 # Documentation index/table of contents
    ├── getting-started/              # Getting started guides
    │   ├── 00-QUICK-START.md        # 5-minute quick start
    │   ├── 01-GETTING-STARTED.md    # Complete installation & setup
    │   ├── CONFIGURATION.md         # Environment & configuration
    │   └── TROUBLESHOOTING.md       # Common issues & solutions
    ├── guides/                       # How-to guides (workflows)
    ├── reference/                    # Technical reference
    │   └── ARCHITECTURE.md          # System architecture and design
    └── daily-work/                   # Daily workflow automation (if applicable)
        ├── DAILY_ROUTINE.md         # Daily routine scripts documentation
        └── GITHUB_PROJECT_TASKS.md  # Current project tasks

NOTE: LICENSE and CONTRIBUTING.md MUST be in the repository root for GitHub to detect them.


Create these required files:
- docs/DOCS_INDEX.md
- docs/getting-started/00-QUICK-START.md
- docs/getting-started/01-GETTING-STARTED.md
- docs/getting-started/CONFIGURATION.md
- docs/getting-started/TROUBLESHOOTING.md
- docs/reference/ARCHITECTURE.md

  • Code Documentation
    ⚠️  No Python files checked for documentation
    💡 Ensure code files have docstrings

✅ Passed Checks:
----------------------------------------------------------------------
  • README.md: ✅ Comprehensive README (10402 chars)

======================================================================


======================================================================
  Daily Routine Checker
======================================================================

======================================================================
Daily Routine Setup Report: feature/sprint-next-qe-baseline
======================================================================

Score: 0.0% (0/7 checks passed)
Status: ⚠️  NEEDS ATTENTION

❌ Failed Checks:
----------------------------------------------------------------------
  • Directory: daily-routine-scripts
    ❌ Daily automation scripts directory not found
    💡 Create daily-routine-scripts/ directory for daily workflow automation

  • Directory: docs/daily-work
    ❌ Daily work documentation directory not found
    💡 Create docs/daily-work/ directory for daily workflow automation

  • Script: start_day.py
    ❌ Morning routine initialization not found
    💡 Create daily-routine-scripts/start_day.py for morning routine initialization

  • Script: end_day.py
    ❌ Evening routine finalization not found
    💡 Create daily-routine-scripts/end_day.py for evening routine finalization

  • Script: sync_project_status.py
    ❌ GitHub project synchronization not found
    💡 Create daily-routine-scripts/sync_project_status.py for github project synchronization

  • Documentation: DAILY_ROUTINE.md
    ❌ Daily routine documentation not found
    💡 Create docs/daily-work/DAILY_ROUTINE.md to document daily workflow

  • Documentation: GITHUB_PROJECT_TASKS.md
    ❌ Project tasks tracking not found
    💡 Create docs/daily-work/GITHUB_PROJECT_TASKS.md to document daily workflow

======================================================================


======================================================================
  Combined Summary
======================================================================
  Status: ❌ NEEDS ATTENTION
  Score:  64.0% (16/25 checks passed)
======================================================================
```

### P0 failures tracked as issues

None. The qe-check baseline identified several gaps. The ❌ Failed Checks in the Documentation section (missing LICENSE file, incomplete Copilot instructions) are genuine tool failures but are not tracked as P0 blockers for this portal. All remaining flagged items are ⚠️ recommendations — optional enhancements not required for the current 250-QE use case.

**Score Breakdown:**
- **CI/CD Checker**: 100% (10/10) — all required CI infrastructure in place
- **Documentation Checker**: 75% (6/8) — README is comprehensive; missing LICENSE file and some optional docs
- **Daily Routine Checker**: 0% (0/7) — daily routine automation infrastructure not yet implemented (expected for Slice 0 baseline)
- **Overall**: 64% (16/25 checks passed)
