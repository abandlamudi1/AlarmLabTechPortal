# Load Test — Lab Tech Portal

Locust 2.30.0 load-test suite for the Lab Tech Portal Docker Compose stack.
Validates that the stack sustains 50 concurrent users without `database is
locked` errors under WAL + Gunicorn workers + Celery worker sharing one SQLite
file per tool (see `docs/CLEANUP_PLAN.md:218`, risk-hotspot entry).

---

## Prerequisites

- Docker and Docker Compose v2
- A checked-out copy of this repo
- A valid `.env` file (copy `.env.example` and fill in the non-Okta vars)

---

## Auth bypass

The portal uses Okta for production SSO.  During load tests, Okta
configuration is intentionally absent so the app sets `LOGIN_DISABLED=True`
at startup and skips all `login_required` checks.

**Do not set `OKTA_ISSUER` in the environment when running load tests.**

This is the same mechanism used by the unit/integration test suite
(`TESTING=True` / `LOGIN_DISABLED=True` in `conftest.py`).

---

## Jira isolation

Some routes (system-locator Jira import, print-request create) can trigger
outbound Jira API calls.  Before running:

```bash
export JIRA_DRY_RUN=true      # or set it in your .env
# OR: leave all JIRA_* vars unset
```

The `docker-compose.load.yml` overlay defaults `JIRA_DRY_RUN=true` but the
application `.env` takes precedence — verify before running.

---

## Production-default request guards: relaxed by the overlay

Two production defaults would otherwise prevent the load test from exercising
the very write path it exists to validate. The `docker-compose.load.yml`
overlay sets these on the `web` service automatically — operators do not need
to set them by hand, but you should be aware that the load-test stack is
**not** a faithful production environment in these two respects:

| Default | Production | Load-test overlay | Why relaxed |
|---------|------------|-------------------|-------------|
| `WTF_CSRF_ENABLED` | `true` | `false` | Locust HttpUser does not fetch CSRF tokens; every POST would 400 |
| `RATELIMIT_DEFAULT` | `60 per minute` (per-remote-addr) | `100000 per minute` | All locust workers share one source IP; the rate limiter would 429 ~49/50 requests in minute 2 |

If you need to load-test the CSRF or rate-limit code paths themselves, run a
separate, narrower scenario with the production defaults in place.

---

## Quickstart — local run

```bash
# 1. Validate the compose YAML (no containers started):
docker compose -f docker-compose.yml -f docker-compose.load.yml config --quiet

# 2. Start the full stack (web, redis, prometheus) + Locust:
docker compose -f docker-compose.yml -f docker-compose.load.yml up -d

# 3. Open the Locust web UI:
open http://localhost:8089
# Set: Number of users = 50, Spawn rate = 5, Host = http://web:8000
# Click "Start swarming"

# 4. Let the test run for 10 minutes, then download the CSV report.

# 5. Tear down:
docker compose -f docker-compose.yml -f docker-compose.load.yml down
```

---

## Quickstart — headless run (CI / scripted)

```bash
docker compose -f docker-compose.yml -f docker-compose.load.yml run --rm \
  locust \
  -f /mnt/locust/locustfile.py \
  --host http://web:${PORT:-8000} \
  --users 50 \
  --spawn-rate 5 \
  --run-time 10m \
  --headless \
  --csv /mnt/locust/results/baseline
```

Output CSVs will appear in `tests/load/results/` (mount a host directory
or copy out of the container after the run).

---

## Running against staging

Replace the `--host` value with the staging URL.  Okta must still be disabled
or a dedicated test-user credential flow must be implemented.  Contact the
portal maintainer before running load tests against any shared environment.

```bash
docker run --rm \
  -v "$(pwd)/tests/load:/mnt/locust:ro" \
  locustio/locust:2.30.0 \
  -f /mnt/locust/locustfile.py \
  --host https://staging.lab-portal.example.com \
  --users 50 \
  --spawn-rate 5 \
  --run-time 10m \
  --headless
```

---

## Task mix

| Category | Approx. share | Tasks included |
|----------|--------------|----------------|
| Reads    | 60 %         | list/dashboard views for all 5 tools |
| Writes   | 30 %         | inventory add, checkout return, RF chamber add, system create, print-request form |
| Jira-touching | 10 %   | system-locator Jira import form (GET only), print-request history |

Jira-touching tasks deliberately use **GET requests only** (form display, not
form submission) so that no outbound Jira API calls occur during the load test.
The POST-based import is not part of the automated mix; operators who want to
test the import submission path must do so manually in a Jira-isolated
environment.

---

## Acceptance criteria (Sprint 8, issue #123)

- [ ] p95 latency for all read endpoints < 500 ms at 50 users
- [ ] p95 latency for write endpoints < 1 000 ms at 50 users
- [ ] Zero `database is locked` errors in `docker compose logs web` during the run
- [ ] Locust error rate < 1 % for all tasks

Record results in `docs/load-test-baseline.md`.
