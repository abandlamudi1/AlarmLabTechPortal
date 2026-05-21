---
name: migrate
description: Run Alembic migrations and ad-hoc SQL against the Dockerized PostgreSQL database. Use for applying migrations, checking status, and executing data fixes.
argument-hint: "[status | sql 'SQL statement' | create 'description']"
allowed-tools: Bash(docker *) Bash(./scripts/db-*.sh*) Bash(mkdir*) Read Write Glob Grep
---

# Database Migration Skill

> **Constants.** Read `.claude/skills/skill-config.yml` for project-specific constants. All `$CONFIG.*` references in this document use values from that file.

> **STATUS: NOT YET APPLICABLE TO lab-tech-portal.**
> This skill targets a Dockerized PostgreSQL + Alembic stack. lab-tech-portal is currently Flask + 5 SQLite databases (see [AGENTS.md](../../../AGENTS.md) §Project Quick Facts). The Postgres + Alembic migration lands in **Slice D-part2** (issues #26–#28). Adapt this skill — container names, alembic.ini path, `FW_ENVIRONMENT` → tool-prefix env-var convention — when that slice is in flight. Do not invoke before then.

Run Alembic database migrations and ad-hoc SQL inside the Docker environment.

## SAFETY RULES (enforced before every invocation)

### 1. Auto-snapshot
Before any operation that touches the schema (upgrade, downgrade, or destructive SQL), ALWAYS run:
```bash
./scripts/db-snapshot.sh
```
If the script does not exist, STOP and tell the user to implement #866 first.

### 2. Downgrade guard
- `downgrade base` and `downgrade -N` where N > 1 are REFUSED unless the user has typed the exact phrase **"yes i want to wipe my dev DB"** in the current conversation turn (not a previous turn).
- If the phrase was not given: explain the risk, show the current row counts, and ask the user to confirm with the exact phrase if they still want to proceed.
- This guard applies regardless of who called the skill (agent or human).

### 3. Environment awareness
Read `FW_ENVIRONMENT` from the environment before any destructive operation:
```bash
docker exec fw-testing-backend printenv FW_ENVIRONMENT 2>/dev/null || echo "development"
```
- **`production`** → REFUSE all destructive operations (downgrade, DROP, TRUNCATE, DELETE FROM) regardless of confirmation. Log the refusal.
- **`staging`** → require the confirmation phrase AND show production-like warnings ("This is STAGING — changes may affect shared data").
- **`development`** → warn-and-confirm for destructive; non-destructive proceeds after snapshot.
- **`test`** → unrestricted (used by CI).

### 4. Row-count diff
Before any upgrade or downgrade, capture row counts for key tables:
```sql
SELECT 'firmware_items' AS tbl, COUNT(*) FROM firmware_items
UNION ALL SELECT 'users', COUNT(*) FROM users
UNION ALL SELECT 'sync_cursors', COUNT(*) FROM sync_cursors
UNION ALL SELECT 'admin_audit_logs', COUNT(*) FROM admin_audit_logs;
```
Show the before/after counts in the output. Flag any unexpected drops (> 10% decrease) with a warning.

### 5. Migration audit log
Append to `./logs/migrations.log` for every invocation:
```
<UTC-timestamp> <FW_ENVIRONMENT> <mode> <args> <before-counts> <after-counts>
```
Create `./logs/` if it doesn't exist. Never fail the migration if logging fails.

---

## Environment Facts (do NOT rediscover these)

| Item | Value |
|------|-------|
| Postgres container | `fw-testing-postgres` |
| Backend container | `fw-testing-backend` |
| DB user | `fw_testing` |
| DB name | `fw_testing` |
| Alembic config | `backend/alembic.ini` |
| Migrations dir | `backend/migrations/versions/` |
| Latest revision file pattern | `NNN_*.py` (zero-padded 3-digit prefix) |

---

## Modes

### Mode 1: Apply migrations (default)
```
/migrate
```
1. Read `FW_ENVIRONMENT` (see safety rule 3)
2. Capture before row counts (rule 4)
3. Run `./scripts/db-snapshot.sh`
4. Run `docker exec fw-testing-backend python -m alembic upgrade head`
5. Capture after row counts; show diff
6. Report which revisions were applied (or "already at head")
7. Append to `./logs/migrations.log`
8. If backend container is not running, tell the user: `docker compose up -d`

### Mode 2: Check status
```
/migrate status
```
1. Run `docker exec fw-testing-backend python -m alembic current`
2. Run `docker exec fw-testing-backend python -m alembic heads`
3. Report whether DB is up-to-date or has pending migrations
4. No snapshot needed for status-only

### Mode 3: Run ad-hoc SQL
```
/migrate sql "UPDATE users SET is_video_qe_team = FALSE"
```
1. For destructive statements (UPDATE, DELETE, DROP, TRUNCATE): apply safety rules 1–3
2. For SELECT-only: proceed without snapshot
3. Run: `docker exec fw-testing-postgres psql -U fw_testing -d fw_testing -c "<sql>"`
4. Display the result

### Mode 4: Downgrade (DANGEROUS — requires confirmation)
```
/migrate downgrade -1
```
1. Apply safety rules 1–3 (snapshot + environment check)
2. If N > 1 or target is `base`: enforce downgrade guard (rule 2)
3. Show before row counts
4. Run downgrade only after all guards pass
5. Show after row counts and flag any unexpected data loss

### Mode 5: Create a new migration file
```
/migrate create "description of the change"
```
1. Find the latest revision number from `backend/migrations/versions/`
2. Create the new file as `backend/migrations/versions/{NNN+1}_{snake_case_description}.py`
3. Template:

```python
"""<Description>.

Revision ID: <NNN+1>
Revises: <NNN>
Create Date: <YYYY-MM-DD>
"""
from alembic import op
import sqlalchemy as sa

revision = '<NNN+1>'
down_revision = '<NNN>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
```

4. Do NOT auto-apply — tell the user to run `/migrate` when ready.

---

## After any migration or SQL change

- If the schema changed (new columns, altered types): remind the user to restart the backend:
  `docker compose restart backend`
- If only data changed (UPDATE/INSERT/DELETE): no restart needed

## Error handling

- If `docker exec` fails with "No such container": check `docker compose ps` and report which services are down
- If alembic fails with a revision conflict: show the error and suggest resolution
- If `db-snapshot.sh` fails: STOP — do not proceed with the migration; report the error and ask the user how to proceed
