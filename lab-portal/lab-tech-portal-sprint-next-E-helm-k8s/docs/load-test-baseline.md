# Load-Test Baseline — Lab Tech Portal

> **Status: PENDING** — Framework merged; baseline run not yet executed.
> The operator will run the 10-minute 50-user baseline after merge and populate
> this document in a follow-up PR.  See `tests/load/README.md` for the runbook.

---

## Environment

| Field | Value |
|-------|-------|
| Date | _TODO_ |
| Operator | _TODO_ |
| Locust version | 2.30.0 |
| Portal image tag / git SHA | _TODO_ |
| Host machine (CPU / RAM) | _TODO_ |
| Docker Desktop / engine version | _TODO_ |
| Compose command used | _TODO_ |
| Test duration | 10 min |
| Number of users | 50 |
| Spawn rate | 5 users/s |
| Gunicorn worker count | _TODO (from .env or Dockerfile)_ |
| Celery worker concurrency | _TODO (from .env)_ |
| SQLite WAL enabled | _TODO (yes/no)_ |

---

## How to run

See `tests/load/README.md` for the full quickstart.  Short version:

```bash
docker compose -f docker-compose.yml -f docker-compose.load.yml up -d
open http://localhost:8089
# Set users=50, spawn rate=5, then start swarming for 10 minutes.
```

---

## Results — Read endpoints (60 % of mix)

| Endpoint | Req count | Median (ms) | p95 (ms) | p99 (ms) | Error % |
|----------|-----------|-------------|----------|----------|---------|
| GET /inventory/ | | | | | |
| GET /checkout/ | | | | | |
| GET /rf-chamber/ | | | | | |
| GET /systems/ | | | | | |
| GET /print-requests/ | | | | | |
| GET /print-requests/requests | | | | | |

---

## Results — Write endpoints (30 % of mix)

| Endpoint | Req count | Median (ms) | p95 (ms) | p99 (ms) | Error % |
|----------|-----------|-------------|----------|----------|---------|
| POST /inventory/add_item | | | | | |
| POST /checkout/1/return | | | | | |
| POST /rf-chamber/add | | | | | |
| POST /systems/new | | | | | |
| GET /print-requests/new | | | | | |

---

## Results — Jira-touching endpoints (10 % of mix)

| Endpoint | Req count | Median (ms) | p95 (ms) | p99 (ms) | Error % |
|----------|-----------|-------------|----------|----------|---------|
| GET /systems/jira-import | | | | | |
| GET /print-requests/requests/history | | | | | |

---

## Aggregate summary

| Metric | Value | Target |
|--------|-------|--------|
| Total requests | | — |
| Requests/sec (peak) | | — |
| Overall error rate | | < 1 % |
| p95 latency — reads | | < 500 ms |
| p95 latency — writes | | < 1 000 ms |
| `database is locked` errors in `docker compose logs web` | | 0 |

---

## How to interpret

- **p95 / p99**: 95th / 99th percentile response time in milliseconds.  A p95
  above the target indicates the stack cannot sustain 50 concurrent users at
  acceptable latency.
- **Error %**: percentage of Locust tasks that received a non-2xx / non-3xx
  response.  Any `database is locked` error will surface as a 500 here.
- **`database is locked`**: grep `docker compose logs web 2>&1 | grep "database is locked"`.
  Zero occurrences is the passing criterion (see `docs/CLEANUP_PLAN.md:218`).

---

## Pass / Fail

| Criterion | Result |
|-----------|--------|
| p95 reads < 500 ms | _TODO_ |
| p95 writes < 1 000 ms | _TODO_ |
| Error rate < 1 % | _TODO_ |
| Zero `database is locked` errors | _TODO_ |
| **Overall** | **_TODO_** |

---

## Notes / observations

_TODO: record any anomalies, worker restarts, Redis errors, or other
observations from the run here._

---

## Follow-up actions

_TODO: list any issues filed as a result of this baseline run._
