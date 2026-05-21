# API Reference

This document describes the HTTP API endpoints of the Lab Tech Portal.

---

## Overview

**Base URL:** `http://localhost:8000` (development) or your production host

**Current API version:** None formally versioned yet. A versioned API (`/api/v1/`) will land in Slice C (Sprint 3).

**Authentication:** Okta OIDC via Flask-Login (see [AGENTS.md](../AGENTS.md) and `.env.example` for configuration).

---

## Status: Scaffold

This is the initial API documentation scaffold. Full endpoint documentation and schema will be added when `/api/v1/` is built in Slice C (Sprint 3).

---

## Current Endpoints (Slice 0–G-part1)

All endpoints are server-rendered HTML (no JSON API yet). The following tool blueprints are registered:

Routes below are derived from `app.py` and the tool blueprints (`tools/*/[tool]_app.py`) at the time of writing. If they drift, the blueprints are the source of truth.

### Inventory (`/inventory`)

- `GET /inventory/` — List all inventory items
- `GET|POST /inventory/add_item` — Create a new item
- `GET|POST /inventory/scan_item` — Scan barcode to look up / update an item

### RF Chamber (`/rf-chamber`)

- `GET /rf-chamber/` — List all chambers
- `GET|POST /rf-chamber/add` — Create a new chamber entry
- `GET|POST /rf-chamber/edit/<barcode>` — Edit an existing chamber by barcode

### Equipment Checkout (`/checkout`)

- `GET /checkout/` — Checkout dashboard / list

### System Locator (`/systems`)

- `GET /systems/` — List systems
- `GET|POST /systems/new` — Create a new system
- `GET|POST /systems/<id>/edit` — Edit an existing system
- `GET|POST /systems/jira-import` — Jira Lab Request import UI

### 3D Print Requests (`/print-requests`)

- `GET /print-requests/` — Landing page
- `GET /print-requests/library/<device_key>` — Device-specific library view
- `GET /print-requests/requests` — Active requests list
- `GET /print-requests/requests/history` — Completed/cancelled history
- `GET /print-requests/requests/<id>` — Request detail
- `GET /print-requests/requests/<id>/files/<file_kind>` — Download attached file
- `GET /print-requests/requests/<id>/preview/<file_kind>` — Inline file preview
- `POST /print-requests/requests/<id>/status` — Update request status
- `GET|POST /print-requests/new` — Create a new request

---

## Planned API Structure (Slice C+)

Slice C will introduce a RESTful `/api/v1/` namespace with JSON request/response bodies:

```
GET    /api/v1/inventory
POST   /api/v1/inventory
GET    /api/v1/inventory/{id}
PATCH  /api/v1/inventory/{id}
DELETE /api/v1/inventory/{id}

GET    /api/v1/rf-chambers
GET    /api/v1/rf-chambers/{id}

... (and so on for all 5 tools)
```

Each endpoint will have:
- OpenAPI 3.0 schema
- Request/response examples
- Error codes and messages
- Rate-limit headers (Slice A)
- RBAC requirements (Slice A+)

---

## Infrastructure Endpoints (Slice B+)

Health and observability endpoints added in Slice B:

- `GET /healthz` — Health check (returns 200 OK with service status JSON)
- `GET /metrics` — Prometheus metrics (added Slice B observability)

---

## Authentication & Authorization

- **Okta OIDC** (Slice A): All endpoints require a valid Okta session
- **RBAC** (Slice A, warn-only initially): Role-based access per tool
- **CSRF protection** (Slice A): POST forms require `csrf_token()`

See [services/okta_auth.py](../services/okta_auth.py) and [services/rbac.py](../services/rbac.py) for implementation.

---

## Rate Limiting (Slice A+)

Endpoints are rate-limited per-user using Flask-Limiter:

- Default: 100 requests per 15 minutes
- Configurable via `RATELIMIT_*` env vars (see `.env.example`)

---

## See Also

- [architecture.md](../architecture.md) — system design
- [DOCKER_RUNBOOK.md](../DOCKER_RUNBOOK.md) — running services
- [AGENTS.md](../AGENTS.md) — development conventions
- [docs/CLEANUP_PLAN.md](../CLEANUP_PLAN.md) — roadmap
