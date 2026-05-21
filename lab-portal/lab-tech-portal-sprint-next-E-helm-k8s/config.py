"""Centralized configuration for the Lab Tech Portal.

Introduced in Slice 0 of docs/CLEANUP_PLAN.md. This module defines a config
class hierarchy (Base / Development / Testing / Production) and a fail-fast
validator that prints a redacted summary on startup.

The module is intentionally **standalone** — it imports only the standard
library and python-dotenv. app.py does not yet consume it; wiring lands in a
follow-up commit so that this introduction is a no-behavior-change addition
that can be reverted on its own.

Future-slice keys (Celery, Postgres, S3) are present here for documentation
and a single source of truth, even when no consumer reads them yet. Each is
annotated with the slice that activates it.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


SECRET_KEY_FIELD_PATTERN = re.compile(
    r"(SECRET|PASSWORD|PAT|TOKEN|KEY)$", re.IGNORECASE
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Env %s is not an int (%r); using default %d", name, raw, default)
        return default


@dataclass
class BaseConfig:
    """Default configuration. Subclasses override per environment."""

    # --- Slice 0: Flask core ---
    FLASK_ENV: str = field(default_factory=lambda: _str("FLASK_ENV", "development"))
    SECRET_KEY: str = field(default_factory=lambda: _str("SECRET_KEY", "dev"))
    DEBUG: bool = False
    TESTING: bool = False
    LOGIN_DISABLED: bool = False

    DATA_DIR: str = field(default_factory=lambda: _str("DATA_DIR", "./data"))
    LOG_LEVEL: str = field(default_factory=lambda: _str("LOG_LEVEL", "INFO"))

    # --- Existing — Okta OIDC ---
    OKTA_CLIENT_ID: str = field(default_factory=lambda: _str("OKTA_CLIENT_ID"))
    OKTA_CLIENT_SECRET: str = field(default_factory=lambda: _str("OKTA_CLIENT_SECRET"))
    OKTA_ISSUER: str = field(default_factory=lambda: _str("OKTA_ISSUER"))
    OKTA_REDIRECT_URI: str = field(default_factory=lambda: _str("OKTA_REDIRECT_URI"))

    # --- Existing — Jira REST ---
    JIRA_URL: str = field(default_factory=lambda: _str("JIRA_URL"))
    JIRA_PAT: str = field(default_factory=lambda: _str("JIRA_PAT"))
    JIRA_DEFAULT_ASSIGNEE: str = field(default_factory=lambda: _str("JIRA_DEFAULT_ASSIGNEE"))

    # --- Slice C: Jira custom field IDs (Issue #72) ---
    # These replace hardcoded constants in services/jira_service.py.
    # Set them in .env to match your Jira Cloud instance's field configuration.
    JIRA_LAB_REQUEST_PROJECT_KEY: str = field(
        default_factory=lambda: _str("JIRA_LAB_REQUEST_PROJECT_KEY", "QENG")
    )
    JIRA_LAB_REQUEST_ISSUE_TYPE_ID: str = field(
        default_factory=lambda: _str("JIRA_LAB_REQUEST_ISSUE_TYPE_ID")
    )
    JIRA_CUSTOMFIELD_LAB_REQUEST_TYPE: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_LAB_REQUEST_TYPE")
    )
    JIRA_CUSTOMFIELD_LEAD_QE_TEAM: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_LEAD_QE_TEAM")
    )
    JIRA_CUSTOMFIELD_LEAD_RD_TEAM: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_LEAD_RD_TEAM")
    )
    JIRA_CUSTOMFIELD_DEADLINE: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_DEADLINE")
    )
    JIRA_CUSTOMFIELD_PLANNED_END_DATE: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_PLANNED_END_DATE")
    )
    JIRA_CUSTOMFIELD_HIGH_LEVEL_ESTIMATE: str = field(
        default_factory=lambda: _str("JIRA_CUSTOMFIELD_HIGH_LEVEL_ESTIMATE")
    )
    JIRA_TRANSITION_DONE_ID: str = field(
        default_factory=lambda: _str("JIRA_TRANSITION_DONE_ID")
    )
    JIRA_TRANSITION_CANCEL_ID: str = field(
        default_factory=lambda: _str("JIRA_TRANSITION_CANCEL_ID")
    )

    # --- Existing — Atlassian MCP (optional) ---
    ATLASSIAN_MCP_BASE_URL: str = field(default_factory=lambda: _str("ATLASSIAN_MCP_BASE_URL"))
    ATLASSIAN_MCP_WORKSPACE: str = field(default_factory=lambda: _str("ATLASSIAN_MCP_WORKSPACE"))
    ATLASSIAN_MCP_TOKEN: str = field(default_factory=lambda: _str("ATLASSIAN_MCP_TOKEN"))

    # --- Existing — Per-tool ---
    RF_CHAMBER_BASE_URL: str = field(default_factory=lambda: _str("RF_CHAMBER_BASE_URL"))
    SYSTEM_LOCATOR_JIRA_CACHE_TTL: int = field(
        default_factory=lambda: _int("SYSTEM_LOCATOR_JIRA_CACHE_TTL", 300)
    )
    PRINT_REQUESTS_UPLOAD_FOLDER: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_UPLOAD_FOLDER")
    )
    PRINT_REQUESTS_CREATE_JIRA: bool = field(
        default_factory=lambda: _truthy(_str("PRINT_REQUESTS_CREATE_JIRA"))
    )

    # --- Slice A: secret extraction (not yet active in code) ---
    SYSTEM_LOCATOR_DELETE_PIN: str = field(
        default_factory=lambda: _str("SYSTEM_LOCATOR_DELETE_PIN")
    )
    PRINT_REQUESTS_DEFAULT_ASSIGNEE: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_DEFAULT_ASSIGNEE")
    )
    PRINT_REQUESTS_DEFAULT_PRIORITY: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_DEFAULT_PRIORITY", "P4: Low")
    )
    PRINT_REQUESTS_DEFAULT_REQUEST_TYPE: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_DEFAULT_REQUEST_TYPE", "Other")
    )
    PRINT_REQUESTS_JIRA_CANCEL_TRANSITION_ID: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_JIRA_CANCEL_TRANSITION_ID")
    )
    PRINT_REQUESTS_JIRA_CLOSE_TRANSITION_ID: str = field(
        default_factory=lambda: _str("PRINT_REQUESTS_JIRA_CLOSE_TRANSITION_ID")
    )
    RBAC_ENFORCEMENT_MODE: str = field(
        default_factory=lambda: _str("RBAC_ENFORCEMENT_MODE", "warn-only")
    )

    # --- Slice A: RBAC group mapping (comma-separated Okta group names) ---
    RBAC_ADMIN_GROUPS: str = field(
        default_factory=lambda: _str("RBAC_ADMIN_GROUPS", "")
    )
    RBAC_LAB_TECH_LEAD_GROUPS: str = field(
        default_factory=lambda: _str("RBAC_LAB_TECH_LEAD_GROUPS", "")
    )
    RBAC_LAB_TECH_GROUPS: str = field(
        default_factory=lambda: _str("RBAC_LAB_TECH_GROUPS", "")
    )

    # --- Slice A: CSRF + rate limiting ---
    WTF_CSRF_ENABLED: bool = field(
        default_factory=lambda: _truthy(_str("WTF_CSRF_ENABLED", "true"))
    )
    RATELIMIT_DEFAULT: str = field(
        default_factory=lambda: _str("RATELIMIT_DEFAULT", "60 per minute")
    )
    RATELIMIT_STORAGE_URI: str = field(
        default_factory=lambda: _str("RATELIMIT_STORAGE_URI", "memory://")
    )

    # --- Slice A: CORS origins (comma-separated) ---
    CORS_ORIGINS: str = field(
        default_factory=lambda: _str("CORS_ORIGINS", "")
    )

    # --- Slice B: Audit log (issue #46) ---
    # AUDIT_LOG_DB_PATH: absolute path to the shared audit SQLite file.
    # Default: DATA_DIR/db/audit.db (resolved at runtime by services/audit_log.py
    # init_app).  Set this env var to redirect audit storage in containerised
    # deployments that mount separate volumes for audit data.
    AUDIT_LOG_DB_PATH: str = field(
        default_factory=lambda: _str("AUDIT_LOG_DB_PATH", "")
    )

    # --- Slice B: Prometheus metrics (issue #32) ---
    # METRICS_ENABLED: when False, /metrics endpoint is not registered.
    # METRICS_NAMESPACE: reserved placeholder — custom metric names use the
    # module-level _NAMESPACE constant in services/metrics.py (set at import
    # time). This field is not currently wired to the exporter.
    METRICS_ENABLED: bool = field(
        default_factory=lambda: _truthy(os.getenv("METRICS_ENABLED", "true"))
    )
    METRICS_NAMESPACE: str = field(
        default_factory=lambda: os.getenv("METRICS_NAMESPACE", "lab_portal")
    )

    # --- Slice H: OpenAPI/Swagger UI (issue #53) ---
    # SWAGGER_ENABLED: when True, mounts flasgger Swagger UI at /api/v1/docs/.
    # Also enabled automatically when app.debug is True.
    SWAGGER_ENABLED: bool = field(
        default_factory=lambda: _truthy(os.getenv("SWAGGER_ENABLED", "false"))
    )

    # --- Slice B: Structured logging (issue #33) ---
    # LOG_FORMAT: 'plain' emits stdlib text logs (dev default); 'json' emits
    # structlog JSON (production default). Can be overridden via env var.
    LOG_FORMAT: str = field(
        default_factory=lambda: _str("LOG_FORMAT", "json" if _str("FLASK_ENV") == "production" else "plain")
    )
    # STRUCTLOG_ENABLED: when False, structlog is imported but logging falls
    # back to stdlib formatters (useful for log aggregators that don't accept JSON).
    STRUCTLOG_ENABLED: bool = field(
        default_factory=lambda: _truthy(_str("STRUCTLOG_ENABLED", "true"))
    )

    # --- Slice A: Secure cookie settings (production only) ---
    SESSION_COOKIE_SECURE: bool = field(
        default_factory=lambda: _truthy(_str("SESSION_COOKIE_SECURE", "false"))
    )
    SESSION_COOKIE_HTTPONLY: bool = field(
        default_factory=lambda: _truthy(_str("SESSION_COOKIE_HTTPONLY", "true"))
    )
    SESSION_COOKIE_SAMESITE: str = field(
        default_factory=lambda: _str("SESSION_COOKIE_SAMESITE", "Lax")
    )

    # === Sessions === (Sprint 8 Issue #30: flask-session Redis backend)
    # SESSION_TYPE: "cookie" (default, backward-compatible) or "redis".
    # Only set SESSION_TYPE=redis in container/prod manifests.
    SESSION_TYPE: str = field(
        default_factory=lambda: _str("SESSION_TYPE", "cookie")
    )
    # SESSION_LIFETIME_SECONDS: session TTL in seconds (default 24h = 86400).
    # Mapped to Flask's PERMANENT_SESSION_LIFETIME (as timedelta in app.py).
    SESSION_LIFETIME_SECONDS: int = field(
        default_factory=lambda: _int("SESSION_LIFETIME_SECONDS", 86400)
    )
    # SESSION_KEY_PREFIX: Redis key namespace — keeps session keys distinct
    # from Celery task keys even if both point at the same Redis instance.
    SESSION_KEY_PREFIX: str = field(
        default_factory=lambda: _str("SESSION_KEY_PREFIX", "lab-portal:session:")
    )

    # --- Slice C: Celery + Redis ---
    REDIS_URL: str = field(default_factory=lambda: _str("REDIS_URL"))
    CELERY_BROKER_URL: str = field(default_factory=lambda: _str("CELERY_BROKER_URL"))
    CELERY_RESULT_BACKEND: str = field(default_factory=lambda: _str("CELERY_RESULT_BACKEND"))

    # --- Sprint 6 Issue #90: Celery worker production tuning ---
    # CELERY_WORKER_CONCURRENCY: number of worker processes (default: CPU count).
    # CELERY_QUEUES: comma-separated queue names for -Q routing (default: "celery").
    # WORKER_PREFETCH_MULTIPLIER: tasks reserved per worker at a time (1 = fair).
    # RESULT_EXPIRES: TTL in seconds before task results are deleted (default: 1 day).
    CELERY_WORKER_CONCURRENCY: int = field(
        default_factory=lambda: _int("CELERY_WORKER_CONCURRENCY", os.cpu_count() or 2)
    )
    CELERY_QUEUES: str = field(
        default_factory=lambda: _str("CELERY_QUEUES", "celery")
    )
    WORKER_PREFETCH_MULTIPLIER: int = field(
        default_factory=lambda: _int("WORKER_PREFETCH_MULTIPLIER", 1)
    )
    RESULT_EXPIRES: int = field(
        default_factory=lambda: _int("RESULT_EXPIRES", 86400)
    )

    # --- Slice G: deployment (not yet active in code) ---
    GUNICORN_WORKERS: int = field(default_factory=lambda: _int("GUNICORN_WORKERS", 4))
    PORT: int = field(default_factory=lambda: _int("PORT", 8000))

    # --- Slice D-part2: Postgres + S3 (not yet active in code) ---
    DATABASE_URL: str = field(default_factory=lambda: _str("DATABASE_URL"))
    # SESSION_REDIS_URL uses DB 1 to keep sessions separate from Celery (DB 0).
    # F12: do NOT alias to CELERY_BROKER_URL — they may share a host but
    # must use different DB numbers.
    SESSION_REDIS_URL: str = field(
        default_factory=lambda: _str("SESSION_REDIS_URL", "redis://redis:6379/1")
    )
    S3_ENDPOINT_URL: str = field(default_factory=lambda: _str("S3_ENDPOINT_URL"))
    S3_BUCKET: str = field(default_factory=lambda: _str("S3_BUCKET"))
    S3_REGION: str = field(default_factory=lambda: _str("S3_REGION", "us-east-1"))
    S3_ACCESS_KEY: str = field(default_factory=lambda: _str("S3_ACCESS_KEY"))
    S3_SECRET_KEY: str = field(default_factory=lambda: _str("S3_SECRET_KEY"))

    # === Object Storage === (Sprint 8, Issue #29)
    # OBJECT_STORAGE_BACKEND: "local" (default) or "s3".
    # "local" writes files to DATA_DIR/uploads/ — no boto3 required.
    # "s3"    writes to an S3-compatible bucket (MinIO on-prem or AWS S3).
    #         Requires S3_BUCKET; optionally S3_ENDPOINT_URL for MinIO.
    OBJECT_STORAGE_BACKEND: str = field(
        default_factory=lambda: _str("OBJECT_STORAGE_BACKEND", "local")
    )


@dataclass
class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True
    # When Okta is unconfigured, app.py already disables login. Mirror that here.
    LOGIN_DISABLED: bool = field(
        default_factory=lambda: not bool(_str("OKTA_ISSUER"))
    )


@dataclass
class TestingConfig(BaseConfig):
    TESTING: bool = True
    DEBUG: bool = True
    LOGIN_DISABLED: bool = True
    # Tests inject DATA_DIR via fixture; this is the in-class default.
    DATA_DIR: str = field(default_factory=lambda: _str("DATA_DIR", "./data-test"))


@dataclass
class ProductionConfig(BaseConfig):
    DEBUG: bool = False
    LOGIN_DISABLED: bool = False
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"


_CONFIG_BY_ENV: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config_class(env_name: str | None = None) -> type[BaseConfig]:
    """Return the config class matching FLASK_ENV (defaults to development)."""
    name = (env_name or os.environ.get("FLASK_ENV") or "development").lower()
    return _CONFIG_BY_ENV.get(name, DevelopmentConfig)


def load_config(env_name: str | None = None) -> BaseConfig:
    """Load .env then construct the appropriate config object."""
    load_dotenv()
    return get_config_class(env_name)()


def validate_config(cfg: BaseConfig) -> list[str]:
    """Return a list of validation error strings. Empty list = valid.

    Only enforces hard requirements:
      - In production: SECRET_KEY must be set and not the default "dev"/"change-me".
      - When JIRA_PAT is set, JIRA_URL must also be set.
      - When any OKTA_* is set, all of OKTA_CLIENT_ID/SECRET/ISSUER/REDIRECT_URI
        must be set (partial Okta config is worse than none).
      - LOG_LEVEL must be a valid logging level name.
    """
    errors: list[str] = []

    if isinstance(cfg, ProductionConfig):
        if not cfg.SECRET_KEY or cfg.SECRET_KEY in {"dev", "change-me"}:
            errors.append(
                "SECRET_KEY must be set to a non-default value in production"
            )

    if isinstance(cfg, ProductionConfig) and cfg.JIRA_PAT and not cfg.JIRA_URL:
        errors.append("JIRA_PAT is set but JIRA_URL is empty")

    okta_values = [
        cfg.OKTA_CLIENT_ID,
        cfg.OKTA_CLIENT_SECRET,
        cfg.OKTA_ISSUER,
        cfg.OKTA_REDIRECT_URI,
    ]
    if any(okta_values) and not all(okta_values):
        errors.append(
            "Partial Okta config detected; all four OKTA_* env vars must be set together "
            "or none of them"
        )

    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if cfg.LOG_LEVEL.upper() not in valid_levels:
        errors.append(f"LOG_LEVEL={cfg.LOG_LEVEL!r} is not a recognized logging level")

    return errors


def _redact_url_userinfo(url: str) -> str:
    """Strip the password component from a URL-shaped string for safe logging."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    userinfo, host_path = rest.split("@", 1)
    if ":" in userinfo:
        user = userinfo.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host_path}"
    return url


def _redact(name: str, value: Any) -> Any:
    if isinstance(value, str) and value and SECRET_KEY_FIELD_PATTERN.search(name):
        return f"<redacted len={len(value)}>"
    # URL-shaped fields (e.g. SESSION_REDIS_URL, CELERY_BROKER_URL, DATABASE_URL)
    # may embed credentials in the userinfo segment. Strip the password before
    # rendering so the config summary log doesn't leak managed-Redis or DB creds.
    if (
        isinstance(value, str)
        and value
        and name.endswith("_URL")
        and "://" in value
        and "@" in value.split("://", 1)[1]
    ):
        return _redact_url_userinfo(value)
    return value


def render_config_summary(cfg: BaseConfig) -> str:
    """Render a multiline string of the config with secrets redacted."""
    lines = [f"--- {type(cfg).__name__} ---"]
    for f in fields(cfg):
        lines.append(f"  {f.name} = {_redact(f.name, getattr(cfg, f.name))!r}")
    return "\n".join(lines)


def init_app(app, cfg: BaseConfig | None = None) -> BaseConfig:
    """Apply a config object to a Flask app, fail fast on errors, log summary.

    Intended wiring (Slice 0b, separate commit):

        from config import init_app
        cfg = init_app(app)
    """
    if cfg is None:
        cfg = load_config()
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        raise ValueError(
            f"Invalid configuration ({len(errors)} error(s)). "
            f"Set the required environment variables and restart."
        )
    for f in fields(cfg):
        app.config[f.name] = getattr(cfg, f.name)
    # Also ensure DATA_DIR exists so the rest of the app can rely on it.
    Path(cfg.DATA_DIR).mkdir(parents=True, exist_ok=True)
    logger.info("Configuration loaded:\n%s", render_config_summary(cfg))
    return cfg
