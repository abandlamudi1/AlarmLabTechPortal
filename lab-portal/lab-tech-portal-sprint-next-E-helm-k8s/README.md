# Lab Tech Portal

Central web portal for internal lab tools. Currently ships with:
- Inventory Tracker (item CRUD with QR labels)
- RF Chamber Database (chamber tracking with scan-to-edit QR codes)
- System Locator with Jira-backed Lab Request import
- 3D Print Requests intake queue with agent-driven Jira sync

## Quick Start

Choose your deployment method:

> **Note:** Option 1 below requires the Docker artifacts (`Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`) shipped in [Slice G-part1 / PR #58](https://github.com/adc-quality/lab-tech-portal/pull/58). Until that PR merges, use Option 2 (local Python).

### Option 1: Docker (Recommended)

**Prerequisites:** Docker 24+ and Docker Compose v2

```bash
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY to a random value
docker compose up -d
# Web UI available at http://localhost:8000
# Logs: docker compose logs -f web
# Stop: docker compose down
```

Data persists across restarts in named Docker volumes (`db-data`, `upload-data`, `generated-data`, `redis-data`).

For hot-reload development:

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
# Edit source files — Flask reloads automatically (no rebuild needed)
```

See [docs/DOCKER_RUNBOOK.md](docs/DOCKER_RUNBOOK.md) for comprehensive Docker operations.

### Option 2: Local Python Environment

1. **Clone the repository** and navigate to the project directory

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your actual credentials:
   - `JIRA_URL`: Your Jira instance URL (e.g., `https://your-company.atlassian.net` or `https://jira.yourcompany.com/jira`)
   - `JIRA_USERNAME`: Your Jira username or email
   - `JIRA_PAT`: Your Jira Personal Access Token or API token ([Get one here](https://id.atlassian.com/manage-profile/security/api-tokens))
   - Other settings as needed (see Configuration section below)

5. **Run the application**:
   ```bash
   flask run
   ```

6. **Access the portal** at `http://localhost:5000`

## Theming

All HTML templates should extend `templates/base.html` to inherit the shared layout, light/dark theme toggle, and global styles.

## Configuration

Environment variables are loaded from a `.env` file (copy `.env.example` to get started). Available settings:

### Flask
- `FLASK_ENV`: Set to `development` or `production`
- `SECRET_KEY`: Change this to a random secret value for session security

### Okta OIDC
Required for Okta SSO authentication:
- `OKTA_CLIENT_ID`: Okta OIDC client ID
- `OKTA_CLIENT_SECRET`: Okta OIDC client secret
- `OKTA_ISSUER`: Okta issuer URL (for example, `https://your-domain.okta.com/oauth2/default`)
- `OKTA_REDIRECT_URI`: Callback URL registered in Okta (for example, `http://localhost:5000/auth/callback`)

### Jira REST API (JiraService)
Required for creating/managing Lab Request tickets directly via REST API:
- `JIRA_URL`: Your Jira base URL (e.g., `https://jira.yourcompany.com/jira`)
- `JIRA_PAT`: Your Personal Access Token from Jira (Admin → Personal Access Tokens → Create token)
  - Uses Bearer token authentication (no username required)

### Atlassian MCP (System Locator Jira Import)
Optional, only needed if using the System Locator's Jira import feature via MCP:
- `ATLASSIAN_MCP_BASE_URL`: MCP base URL
- `ATLASSIAN_MCP_WORKSPACE`: MCP workspace identifier
- `ATLASSIAN_MCP_TOKEN`: MCP authentication token

### System Locator
- `SYSTEM_LOCATOR_JIRA_CACHE_TTL`: Optional cache window in seconds for Jira fetches (defaults to 300)
- `SYSTEM_LOCATOR_JIRA_STATUS_MAP`: Optional dict (Flask config) mapping Jira workflow statuses to System Locator states (Active, Maintenance, Broken, Incomplete, Decommissioned)
- `SYSTEM_LOCATOR_JIRA_FIELD_*`: Override Jira custom field keys used for import. Supported suffixes include `CID`, `LOGIN`, `IMEI`, `MAC`, `CAMERA_SERIAL`, `BOARD_SERIAL`, `BUILDING`, `ROOM`, and `SUB_LOCATION`

### RF Chamber
- `RF_CHAMBER_BASE_URL`: Optional absolute URL used when generating RF chamber QR codes. Set this to the production host (for example, `https://portal.example.com`) so printed codes remain valid across deployments

### Print Requests
- `PRINT_REQUESTS_UPLOAD_FOLDER`: Optional override for where uploaded 3D model files are stored; defaults to `tools/print_requests/uploads` if unset
- Copy `.env.example` to `.env` in each environment and supply values for the Flask secret key plus the optional `RF_CHAMBER_BASE_URL` override.
- Static assets currently ship prebuilt; if you customize them, run `python tools/build_static.py` (see below) before deploying so Flask serves the latest bundle.
- On first boot, initialize local SQLite files by running `python tools/setup_datastores.py` to create the inventory and RF chamber databases with seed data.

## Development

See `docs/onboarding-runbook.md` for a full environment bootstrap checklist.

### Local setup

```bash
python -m venv venv
venv/Scripts/activate  # Windows
pip install -r requirements.txt
python app.py
```

### Testing

Tests use pytest with isolated temporary databases:

```bash
# Run all safe tests (excludes Jira ticket creation)
python -m pytest

# Run specific Jira integration tests (creates REAL tickets)
pytest -m creates_jira_tickets
```

The suite seeds sample inventory and RF chamber records to verify routing, validation, and QR code behavior.

⚠️ **Important**: By default, tests that create real Jira tickets are excluded. See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) for detailed testing instructions, including how to run Jira integration tests.

#### Test Coverage

CI enforces a minimum of **70% test coverage per package** on business-logic packages, currently `tools/` and `tasks/`. `services/` is tracked but the gate is deferred until it reaches 70% (TODO #133). Local runs measure coverage without enforcement so you can see the numbers without breaking your iteration loop.

```bash
# Install dev dependencies (if not already installed)
pip install -r requirements-dev.txt

# Measure coverage locally (no gate enforcement)
python -m pytest --cov=tools --cov=services --cov=tasks --cov-report=term-missing

# Generate an XML coverage report (e.g. for IDE integration)
python -m pytest --cov=tools --cov=services --cov=tasks --cov-report=xml

# To preview the per-package gate locally, run after a normal coverage run:
python -m coverage report --include='tools/*' --fail-under=70
python -m coverage report --include='tasks/*' --fail-under=70
```

In CI, each enabled package is gated independently via `coverage report --include=<pkg>/* --fail-under=70` against the test run's data file. The combined `coverage.xml` is uploaded as a CI artifact (`coverage-xml`) on every run. See `.github/workflows/ci.yml` for the exact invocations and `pytest.ini` for the coverage config.

### Jira → System Locator Import

The System Locator now includes a **Jira Import** page that reads Lab Request issues via the Atlassian MCP. Provide optional project filters, date ranges, or explicit issue keys to preview potential changes before confirming. Each imported issue creates or updates a System record, storing:

- Jira summary → system name
- Jira description → notes
- Physical location fields (building, room, sub-location); missing values mark the system status as *Incomplete*
- Identifiers (CID, login, IMEI, MAC, camera/board serials) plus the Jira key

Identifier conflicts with other active systems are surfaced in the preview and skipped during import so manual follow-up is required. Configure field IDs or status mappings with the environment variables listed above. The MCP client caches results briefly (`SYSTEM_LOCATOR_JIRA_CACHE_TTL`) to minimize repeated fetches while iterating on the same preview.

### 3D Print Requests & Jira Sync

Use the **3D Print Requests** tool to capture structured part requests before routing them to Jira. The portal provides:

- `/print-requests/` list view summarizing requester, team, request type, print status, and Jira status.
- `/print-requests/new` form supporting the three request types (existing model, file upload, new design). Uploaded `.stl`, `.3mf`, and optional design images are saved locally and referenced in the request record.
- `/print-requests/requests/<id>` detail view for reviewing a request and downloading attachments.

Requests are saved to `tools/print_requests/print_requests.db` with fields:

| Field | Notes |
| --- | --- |
| `requester` | Required string |
| `team` | Optional team/group |
| `request_type` | `existing_model`, `upload_file`, or `new_design` |
| `description` | Structured notes composed from the form |
| `uploaded_file_path` | Absolute path to uploaded model, nullable |
| `uploaded_image_path` | Absolute path to uploaded design image, nullable |
| `print_status` | Design, Printing, Cancelled, or Closed |
| `jira_sync_error` | Error string if Jira creation/transition fails |
| `jira_ticket_key` | Jira issue key once synced |
| `created_at` | UTC timestamp stored as ISO string |

#### Running the Jira sync agent

Ticket creation now runs automatically when a request is submitted (when Jira credentials are configured). You can still run the agent script to retry any pending requests that failed Jira creation:

```bash
export ATLASSIAN_MCP_BASE_URL=...        # or set in environment
export ATLASSIAN_MCP_WORKSPACE=...
export ATLASSIAN_MCP_TOKEN=...
python tools/print_requests/scripts/sync_to_jira.py --limit 10
```

Key behavior:

- Fetches requests without a Jira key (`jira_ticket_key IS NULL`).
- Creates a Lab Request issue via the Atlassian MCP with a summary prefixed `3D Print Request:` and a detailed description including requester metadata.
- Uploads model attachments when `uploaded_file_path` exists.
- Uploads design images when `uploaded_image_path` exists.
- Calls back into the local datastore (`db.mark_synced`) to store the newly created Jira issue key. The portal list then shows the key instead of “Not yet created”.

You can omit `--limit` to sync all pending items. Errors (e.g. missing files) are logged to stderr so the operator can retry after correcting the source data.