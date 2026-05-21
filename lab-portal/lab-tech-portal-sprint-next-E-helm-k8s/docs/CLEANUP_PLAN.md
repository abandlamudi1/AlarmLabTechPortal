# Lab Tech Portal — Cleanup to Production-Grade for 250 QEs

**Status:** Approved 2026-05-12
**Authors:** Stephen Nodder + AI architecture assist
**Supersedes (reframes, does not delete):** [docs/CONTAINERIZATION_ROADMAP.md](CONTAINERIZATION_ROADMAP.md)
**Tracker:** [GitHub Project #23 — Lab Tech Portal Tracker](https://github.com/orgs/adc-quality/projects/23)

---

## Context

The lab-tech-portal started as two things at once: an attempt to solve real lab-tech responsibility monitoring **and** a personal "first AI-assisted project" learning exercise. Both goals were met, but the codebase now exhibits classic learning-project anti-patterns: hardcoded PIN `"9420"` in source, absolute filesystem paths stored in DB rows, five SQLite files living inside the source tree, `init_db()` running as a side effect of `import`, Flask dev-server only, synchronous Jira calls in the HTTP path, no RBAC, no audit trail, no containers.

Five real tools have shipped — **Inventory, RF Chamber, Equipment Checkout, System Locator (with Jira-Lab-Request import), and 3D Print Requests** — plus the **Daily Routine Scripts** that bracket every contributor's day. The business logic is sound and useful; the platform underneath it is not.

The maintainer is concurrently authoring/polishing three sibling guides at `/Users/snodder/dev/Guides/`:

1. **qe-repo-ai-assisted-guide** — scaffolding compliance (`qe-check` CLI)
2. **qe-architecture-ai-assisted-guide** — pattern catalog (auth, data-layer, observability, external-api-resilience, frontend, real-time, deployment)
3. **qe-kubernetes-ai-assisted-deployment-guide** — Docker / Helm / ArgoCD / SealedSecrets

…glued by **QE-AI-Project-Organization** (daily routine + `org_state.json`). These guides exist precisely for this kind of cleanup, and the cleanup is a chance to harden the guides themselves. This is not a refactor; this is the *first canonical adoption* of the guide stack at depth.

**Target outcome:** lab-tech-portal supports **250 QEs** on Kubernetes via the full 4-phase trajectory in [CONTAINERIZATION_ROADMAP.md](CONTAINERIZATION_ROADMAP.md), reframed and tracked through the architecture guide's pattern catalog, with the cleanup work also producing concrete PRs back to the guide repos.

---

## Approach (confirmed decisions)

- **Reframe through the guides.** The existing [CONTAINERIZATION_ROADMAP.md](CONTAINERIZATION_ROADMAP.md) and Project #23 stay as the technical backbone. Every existing item is re-grouped by guide pattern and re-labeled; gaps the guides reveal become new items.
- **Done bar = full 4-phase roadmap.** Phases 1–4 → containerized, PostgreSQL, S3/MinIO, k8s manifests, Prometheus. ~8 sprints.
- **Use AND improve the guides.** Each slice maintains a [guide-friction.md](guide-friction.md) log. End of each slice → at least one PR against the relevant guide repo. Lab-tech-portal becomes a cited canonical reference in pattern docs (target: 6+ patterns cite it by end).
- **Patterns-first slicing.** Cleanup is organized by architecture-guide pattern, not by tool. Each slice must explicitly cover all 5 tools (matrix table in the slice PR).

---

## Slice catalog

Each slice is a unit of work scoped to one pattern domain. Slices span multiple sprints; the **Sprint Sequence** below schedules them.

### Slice 0 — Baseline & Scaffolding

**Apply:** `qe-repo-ai-assisted-guide` (run `qe-check .` and `qe-check-cicd` / `qe-check-docs` / `qe-check-routine`) + architecture guide `templates/agents-md/AGENTS.md.template` + `templates/workflows/` + `templates/daily-routine/`.

**Scope:**

- Instantiate `AGENTS.md` at repo root with portal-specific rules (5-tool blueprint convention, PIN-removed, deferred init).
- Copy `templates/workflows/{merge-and-review,multi-agent-worktree,pr-review-tiered,worktree-lessons-learned}.md` → [docs/workflows/](workflows/).
- Align `daily routine scripts/` with guide convention [scripts/daily-routine/](../scripts/daily-routine/) (rename + add README crosslink, preserve git history).
- **Config consolidation (Phase 1.7/1.8/1.10):** new `config.py` with `BaseConfig` / `DevelopmentConfig` / `ProductionConfig`, env-var startup validation that fails fast with redacted-secret printout, comprehensive `.env.example`.
- **Deferred init (D4, Phase 1.3):** all `_ensure_db()` / `init_db()` moves out of module-level into `init_app(app)`; CI test that `import tools.<x>` writes nothing to disk.
- **`.dockerignore` stub** (so Slice G is lighter).

### Slice A — Identity, Access & Web Security

**Apply:** `docs/patterns/auth/multi-mode-auth.md` (architecture guide).

**Scope:**

- **Secret extraction (D7, Phase 1.5):** PIN `"9420"` → `SYSTEM_LOCATOR_DELETE_PIN`; default assignee `"bbrice"` → env var; default priority/request-type → env vars; `SECRET_KEY` mandatory in prod via startup validation.
- **RBAC tiers:** `viewer` / `lab-tech` / `lab-tech-lead` / `admin`, mapped from Okta groups. Routes annotated with `@requires_role("admin")`. **Dry-run / warn-only mode** for one sprint before enforcement.
- **Web security hardening (CC4):** Flask-WTF CSRF on POST routes, Flask-Limiter on all routes, secure cookie flags in prod, Content-Security-Policy headers.
- **Session externalization (D14):** deferred to Slice D-part2 (Redis-backed flask-session); Slice A only documents the seam.

### Slice B — Observability

**Apply:** `docs/patterns/observability/audit-logging.md` (architecture guide).

**Scope:**

- Structured JSON logging via `structlog` (CC1).
- Request-correlation ID middleware (`X-Request-ID` header propagated through logs and into Celery later).
- `/healthz` (liveness) + `/readyz` (readiness with DB connectivity check) — D5 + Phase 1.6.
- **Audit log table** (`audit_log` in shared DB) — entries for: system_locator hard-delete, print_request status changes, checkout/return, inventory adjustments, RF chamber edits, system creates/edits.
- **Prometheus metrics endpoint** (`/metrics`) — instrument HTTP latency, Jira call latency, Celery queue depth (Phase 4.6, pulled forward so Slice C has visibility).

### Slice C — External-API Resilience & Async (Celery + JSON API skeleton)

**Apply:** `docs/patterns/external-api-resilience/token-bucket-rate-limiting.md` (architecture guide).

**Scope:**

- **Celery + Redis** broker/result backend (Phase 2.1, 2.2).
- **Jira service refactor** ([services/jira_service.py](../services/jira_service.py)): field IDs from env (D7), transition IDs from env, `requests.adapters.HTTPAdapter` with `urllib3.Retry`, token-bucket rate limiter, exception-hierarchy preserved.
- **Async Jira tasks** (Phase 2.3): `tasks.create_jira_ticket`, `tasks.upload_jira_attachment`, `tasks.transition_jira_ticket`, `tasks.sync_jira_import`. All with retry + idempotency keys.
- **Task-status tracking** (Phase 2.4): `task_status` + `task_id` columns on `print_requests`; status API endpoints.
- **JSON API skeleton (`/api/v1/`)** — CC3 + Phase 3.2 pulled forward. Initially only task-status endpoints + read-only list endpoints; full parity deferred. Required so the UI can poll without reload.
- **UI minimal change:** print-request submission shows "Processing…" with poll (Phase 2.7).

### Slice C2 — Scheduled Work

**Apply:** Same pattern as C plus new guide-feedback pattern *idempotent-periodic-sync* (proposed below).

**Scope:**

- **Celery Beat schedule** (Phase 2.5).
- `periodic.sync_jira_systems` — System Locator pulls new Lab Requests every 15 min.
- `periodic.check_stale_checkouts` — Checkout flags overdue items daily 9 AM.
- `periodic.backup_databases` — daily 2 AM SQLite copy to backup volume (interim, until Postgres).
- `periodic.cleanup_temp_uploads` — weekly orphan-file purge.
- **Idempotency layer** on all periodic tasks (key = Jira issue key for sync; date for backups).

### Slice D-part1 — Data-Layer Foundations (Docker-blocking)

**Apply:** `docs/patterns/data-layer/redis-connection-lifecycle.md` (architecture guide) + new guide patterns proposed below.

**Scope:**

- **`DATA_DIR` centralization** (D1, Phase 1.1) across all 5 tools.
- **Relative paths in DB** for print-request uploads (D2, Phase 1.2); rewrite `send_file()` routes to resolve `UPLOAD_DIR + relpath`.
- **Inline schema restructure** (D17, Phase 1.9): Inventory + RF Chamber gain their own `db.py` modules matching the other 3 tools.
- **WAL mode + busy_timeout** (D18, Phase 3.7) on all SQLite opens.
- **Connection lifecycle** (D8): Flask `g`-scoped connection + `teardown_appcontext`. Redis lifecycle from the canonical pattern doc.
- **SQLAlchemy introduction** (read-only models first, scoped to Checkout as spike).
- **QR code generation paths** (Inventory + RF Chamber) moved out of source tree into `DATA_DIR/generated/`.
- **RF Chamber CSV seed** (`tools/rf_chamber/data/rf_chambers.csv`) moved under `DATA_DIR` or fronted by an Alembic seed.

### Slice D-part2 — Data-Layer Maturation (K8s-blocking)

**Scope:**

- **SQLAlchemy ORM** for all 5 tools (Phase 4.1).
- **Alembic migrations** replace ad-hoc `_migrate_schema()` (Phase 4.2, D15). Baseline migration captures current schema state; per-tool migration history forward.
- **SQLite → PostgreSQL migration** (Phase 4.1): one PG instance, schema-per-tool or shared schema with `tool_` prefix. Data migration script + idempotent reruns.
- **Object storage** for uploads + QR codes (Phase 4.3): S3/MinIO via boto3, abstracted behind a storage interface.
- **Session externalization** (D14, Phase 4.4): flask-session backed by Redis (the seam established in Slice A is now filled).
- **Connection pooling** (Phase 4.7): SQLAlchemy `pool_size`, `max_overflow`, `pool_recycle`.

### Slice G-part1 — Docker Compose Stack

**Apply:** `qe-kubernetes-ai-assisted-deployment-guide` (Docker portion).

**Scope:**

- **Gunicorn** as WSGI server (D3, Phase 1.4).
- **Multi-stage Dockerfile** (Phase 3.1) with `base` / `web` / `worker` / `beat` targets.
- **`docker-compose.yml`** (Phase 3.2): web + worker + beat + redis. Volume mounts for `db-data` / `upload-data` / `generated-data`.
- **`docker-compose.dev.yml`** overlay (Phase 3.6).
- **`wsgi.py` + `entrypoint.sh`** (Phase 3.4, 3.5).
- **GitHub Actions Docker build** (Phase 3.8); image pushed to ghcr.io.
- Health-check wiring on all containers (Phase 3.1 HEALTHCHECK + compose `healthcheck`).
- **Acceptance:** `docker compose up` runs the full stack with the existing SQLite WAL files (post D-part1) and serves 250 users on a single host.

### Slice G-part2 — Kubernetes Readiness

**Scope:**

- **Helm chart** at `charts/lab-tech-portal/` (Phase 4.5).
- Deployments: `web` (2+ replicas, HPA on CPU/mem), `worker` (2 replicas), `beat` (1 replica).
- Services + Ingress (nginx/traefik) + TLS.
- ConfigMap (non-secret config) + **SealedSecrets** for secrets (per Step 2 guide).
- PostgreSQL + Redis as in-cluster services (or external managed if available).
- PersistentVolumeClaims for PG + Redis.
- **ArgoCD application manifest** for GitOps deploy.
- **CronJob: `pg_dump` to object storage** (Phase 4.8).

### Slice H — Continuous Closure (cross-cutting, not end-dump)

**Apply:** `qe-repo-ai-assisted-guide` DocumentationChecker + architecture guide pattern-library philosophy.

**Scope (per-slice contributions, plus final sweep):**

- **Test discipline:** every slice ships ≥5 new tests; coverage delta non-negative; integration suite via `docker-compose.test.yml` (CC5).
- **API documentation** (OpenAPI via apispec) generated from the JSON API blueprints (Slice C onward).
- **Runbook** for Docker Compose ops (start/stop/logs/backup/restore) — written in Slice G-part1.
- **Runbook** for Kubernetes ops — written in Slice G-part2.
- **architecture.md** rewritten to match end-state.
- **guide-friction.md** consolidated into final guide-feedback PRs.
- **`qe-check . --verbose` green** on all three checkers.
- **Design system pattern (Issue #103):** portal design system + a11y audit shipped in PR for Issue #103 (Sprint 6 Wave 1 Stream H); `docs/references/design-system-fw/` snapshot included in-repo. Architecture-guide pattern `frontend/design-system-for-flask-templates.md` is a **follow-on PR** in `qe-architecture-ai-assisted-guide` (out of scope for this PR). Key findings — **fixed in this PR**: `--body-text` undefined variable (aliased to `var(--text)`); `--focus-ring` token added (replaces hardcoded rgba in `input:focus`); `--status-*-color` tokens added to `:root` + `.dark-mode`; `--muted-text` darkened to clear WCAG AA. **Open (follow-on work):** template migration to `--status-*-color` tokens; no skip-to-main link; no `<nav>` landmark.

### Slices E (Frontend SPA) and F (WebSocket Real-Time) — **deferred to v2**

The JSON API skeleton from Slice C plus polling is sufficient for 250 internal QEs. Revisit after launch if telemetry shows polling is painful.

---

## Sprint Sequence (8 sprints)

| Sprint | Slice(s) | Key deliverables | Visible value |
|---|---|---|---|
| **1** | **Slice 0** | qe-check green-ish, `AGENTS.md`, `config.py`, `.env.example`, deferred-init CI test, `docs/workflows/` populated, daily-routine renamed | Repo passes guide baseline; no more spaghetti at import time |
| **2** | **Slice A** | PIN out of source, RBAC tiers (warn-only this sprint), CSRF, rate limiting, secure cookies | "Why is `9420` in source?" question answered; admin-only routes gated |
| **3** | **Slice B** | Structured JSON logs, request IDs, healthz/readyz, audit log, /metrics | Correlated logs across tools; ops can wire up Splunk/Grafana |
| **4** | **Slice D-part1** + **SQLAlchemy spike on Checkout** | DATA_DIR, relative paths, WAL, deferred init enforced, inline schemas merged, Checkout on SQLAlchemy | Portal runs from any DATA_DIR; spike proves D-part2 feasibility |
| **5** | **Slice C** + **Slice C2** | Celery + Redis, async Jira tasks with retry+idempotency, JSON API skeleton, Celery Beat scheduled tasks | Print-request submit no longer blocks; periodic Jira sync running |
| **6** | **Slice G-part1** | Multi-stage Dockerfile, docker-compose.yml + dev overlay, CI builds image, Gunicorn live | `docker compose up` ships the portal; ready for 250 users on one host |
| **7** | **Slice D-part2** | SQLAlchemy across 5 tools, Alembic baseline + history, PG migration, S3/MinIO uploads, Redis session store | Replica-safe; ready for k8s multi-pod |
| **8** | **Slice G-part2** + **Slice H closure** | Helm chart, SealedSecrets, ArgoCD, HPA, integration test suite, runbooks, guide PRs merged | Portal on k8s; cleanup officially shipped |

**Slice A enforcement** (turning RBAC warn-only off) lands in Sprint 3 alongside Slice B's audit logging.

---

## Definition of Done per slice

A slice is shipped only when **all** are true:

- [ ] **Pattern cited in code.** Every relevant module has a header comment `# Pattern: docs/patterns/<cat>/<name>.md` pointing at the guide pattern adopted.
- [ ] **5-tool coverage matrix in PR description.** Table rows: Inventory / RF Chamber / Checkout / System Locator / Print Requests. Cell values: Applied / Done / N/A-with-reason.
- [ ] **qe-check ≥ pre-slice score** with no new exceptions un-tracked.
- [ ] **Tests:** existing 36+ pass, ≥5 new tests added, coverage delta non-negative.
- [ ] **One D1–D20 deficiency retired** from [CONTAINERIZATION_ROADMAP.md](CONTAINERIZATION_ROADMAP.md) (struck through in roadmap update).
- [ ] **Observable artifact.** Curl output, screenshot, or log line attached to the PR demonstrating the new behavior.
- [ ] **Rollback documented** in a `changelogs/CHANGELOG_<date>_<contributor>.md` entry: which env var disables the change, what the fallback looks like.
- [ ] **Guide-friction note** appended to `docs/guide-friction.md` for anything in the pattern doc that was unclear, missing, or wrong.
- [ ] **Project #23 issue closure.** Every issue touched is closed or explicitly deferred with a comment.
- [ ] **Daily-routine integrity.** `start_day.sh` / `end_day.sh` still run cleanly post-slice.

---

## Risk hotspots & mitigations

| Risk | Slice | Mitigation |
|---|---|---|
| **Postgres + Alembic + S3 in one sprint** (highest) | D-part2 | **3-day spike in Sprint 4** on Checkout (smallest schema): SQLAlchemy model + Alembic baseline + data round-trip. If spike struggles → D-part2 scoped to Postgres only; S3 slides to Sprint 8. |
| **Celery worker re-imports the app** and re-triggers any remaining import-time `init_db()` → duplicate-init races | C | Slice 0's deferred-init CI test is a **hard gate** before Sprint 5 starts. |
| **`database is locked`** under load with WAL + Gunicorn workers + Celery worker sharing one SQLite file | D-part1 / G-part1 | **1-day load-test spike in Sprint 4** before declaring D-part1 done. If brittle, accelerate D-part2 / Postgres. |
| **Jira-import double-write** between manual button and periodic Celery Beat job | C2 | Idempotency key = Jira issue key; advisory lock or `INSERT … ON CONFLICT DO UPDATE` after Postgres. |
| **RBAC retrofit blast radius** | A | One full sprint in warn-only mode (logs would-be denials without blocking); enforcement flag flips in Sprint 3. |
| **Daily-routine drift** vs. `org_state.json` schema | 0, H | Slice 0 commits the renamed `scripts/daily-routine/` + an `org_state.json` schema validator in CI. |
| **Guide repos move out from under us** while this work is in flight | All | Pin guide-repo SHAs in `AGENTS.md`; update pins deliberately, never on `main`. |
| **CONTAINERIZATION_ROADMAP.md becomes stale** | All | Treat the roadmap as the per-issue authority and this plan as the per-slice authority; update the roadmap's D1–D20 table at the end of each slice with strikethroughs. |

---

## Project #23 reorganization (one-time, in Sprint 1)

- Add slice labels: `slice-0-baseline`, `slice-a-auth`, `slice-b-observability`, `slice-c-resilience`, `slice-c2-scheduled`, `slice-d-part1`, `slice-d-part2`, `slice-g-part1`, `slice-g-part2`, `slice-h-closure`.
- Add `guide-friction` label for guide-improvement issues.
- Add a "Pattern doc" custom text field per issue → URL to the pattern doc the issue applies.
- Re-bucket the existing 40 issues into the slice labels per the mapping above (e.g., Project 23's "Centralize DATA_DIR" → `slice-d-part1`; "Add Redis as broker" → `slice-c`; "Migrate to PostgreSQL" → `slice-d-part2`).
- Add new issues for items the guides reveal but the roadmap missed: QR generation paths (D), RF chamber CSV seed (D), stale-checkout detection (C2), Jira attachment as separate Celery task (C), RBAC warn-only mode (A), guide-feedback PRs (per slice).

---

## Guide-improvement deliverables (feedback loop)

Each will be a PR against the corresponding guide repo, sourced from [guide-friction.md](guide-friction.md). Priority order:

1. **NEW pattern:** `data-layer/sqlite-to-postgres-migration.md` (highest value; reusable by every QE app graduating to k8s). Driven by Slice D-part2.
2. **NEW pattern:** `data-layer/data-directory-and-relative-paths.md`. Driven by Slice D-part1.
3. **NEW pattern:** `security/secret-extraction.md` (PIN-in-source is generic). Driven by Slice A.
4. **NEW pattern:** `external-api-resilience/idempotent-periodic-sync.md`. Driven by Slice C2.
5. **Auth pattern appendix:** retrofit playbook + warn-only RBAC mode. Driven by Slice A.
6. **Audit-logging pattern addendum:** 5-tool worked example linking to portal source. Driven by Slice B.
7. **`AGENTS.md.template` addition:** tool-by-tool coverage-matrix block for multi-tool repos. Driven by Slice 0.
8. **`org_state.json` schema additions** for the QE-AI-Project-Organization repo (whatever fields turn out to matter for daily-routine scripts to consume). Driven by Slice 0 + H.

---

## Critical files

**Existing — to be modified:**

- [app.py](../app.py)
- [architecture.md](../architecture.md) — rewrite in Slice H
- [CONTAINERIZATION_ROADMAP.md](CONTAINERIZATION_ROADMAP.md) — update D1–D20 table per slice
- [services/jira_service.py](../services/jira_service.py) — 671-line refactor in Slice C
- [services/okta_auth.py](../services/okta_auth.py) — extended in Slice A
- [tools/system_locator/system_locator_app.py](../tools/system_locator/system_locator_app.py) — PIN extraction (line ~435)
- [tools/system_locator/db.py](../tools/system_locator/db.py), [tools/print_requests/db.py](../tools/print_requests/db.py), [tools/checkout/db.py](../tools/checkout/db.py) — DATA_DIR + WAL + ORM
- [tools/inventory/inventory_app.py](../tools/inventory/inventory_app.py), [tools/rf_chamber/rf_chamber_app.py](../tools/rf_chamber/rf_chamber_app.py) — extract inline schemas → `db.py`
- [tools/print_requests/print_requests_app.py](../tools/print_requests/print_requests_app.py) — relative paths, Celery wiring, default-assignee env
- [conftest.py](../conftest.py) — update for new DATA_DIR + Celery test fixtures
- [tools/build_static.py](../tools/build_static.py) — fold into entrypoint
- [scripts/daily-routine/](../scripts/daily-routine/) — relocated from `daily routine scripts/` in Slice 0 (done)

**New — to be created:**

- `AGENTS.md` (repo root) — instantiated from architecture-guide template
- `config.py` — env-class config
- `wsgi.py` — Gunicorn entry
- `entrypoint.sh` — startup script
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.test.yml`
- `services/audit_log.py`, `services/rbac.py`, `services/storage.py`
- `tasks/jira_tasks.py`, `tasks/periodic.py`, `celery_app.py`
- `api/v1/__init__.py` + per-tool blueprints
- `alembic/` + `alembic.ini`
- `models/` (SQLAlchemy)
- `charts/lab-tech-portal/` (Helm)
- `docs/workflows/` (from architecture guide)
- `docs/guide-friction.md`
- `docs/runbook-docker.md`, `docs/runbook-k8s.md`
- `.github/workflows/docker.yml`

**Existing utilities to reuse (do NOT rewrite):**

- `LabRequestIngestionClient` / `JiraServiceLoader` abstractions in [tools/system_locator/](../tools/system_locator/)
- `JiraService` exception hierarchy in [services/jira_service.py](../services/jira_service.py)
- Okta `graceful_degradation` fallback in [services/okta_auth.py](../services/okta_auth.py)
- Daily-routine config parser in `start_day.py` / `end_day.py` (relocate, don't rewrite)

---

## Verification

End-to-end checks performed at the end of each sprint (per the DoD list above), plus a launch-readiness gate at end of Sprint 8:

1. **`qe-check . --verbose`** returns green on cicd, docs, and daily-routine checkers.
2. **`docker compose up`** runs the full stack end-to-end; all five tools accessible; auth flow works; Jira print-request submit completes async; healthz + readyz return 200; metrics endpoint returns Prometheus format.
3. **Helm chart deploys** to a dev k8s cluster; HPA + ingress + SealedSecrets resolved; pods come up healthy; pg_dump CronJob runs.
4. **Load test** to ≥50 concurrent users on Docker Compose (extrapolated for 250) without `database is locked` after Slice D-part2.
5. **Project #23**: every issue is either closed or labeled `v2` with rationale. New issues are slice-tagged.
6. **Guide repos**: ≥4 PRs merged across `qe-architecture-ai-assisted-guide`, `qe-repo-ai-assisted-guide`, `QE-AI-Project-Organization` from the friction log; ≥6 pattern docs cite lab-tech-portal as a canonical reference.
7. **Tests**: `python -m pytest` is green; coverage report shows ≥70% on `tools/`, `services/`, `tasks/`, `api/`.
8. **Runbook smoke**: a contributor following only `docs/runbook-docker.md` can stand up the portal cold. Same for `docs/runbook-k8s.md`.
