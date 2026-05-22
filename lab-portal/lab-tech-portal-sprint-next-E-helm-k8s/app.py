import logging
import os
import sqlite3
import time
import uuid
from typing import Optional
from urllib.parse import quote as _url_quote, urlparse

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config as _config
import services.audit_log as _audit_log_module
import services.metrics as _metrics_module
import services.object_storage as _object_storage_module
from services.okta_auth import OktaAuthError, OktaAuthService
from services.local_auth import verify_local_user, create_local_user
from services.logging_config import bind_request_context, clear_request_context, get_logger, init_logging
from services.rbac import requires_role as _requires_role
from celery_app import make_celery

# Load environment variables from .env file
load_dotenv()

from tools.inventory.inventory_app import inventory_bp
from tools.inventory.inventory_app import init_app as _inventory_init_app
import tools.inventory.db as _inventory_db
from tools.rf_chamber.rf_chamber_app import rf_chamber_bp
from tools.rf_chamber.rf_chamber_app import init_app as _rf_chamber_init_app
import tools.rf_chamber.db as _rf_db
from tools.checkout.checkout_app import checkout_bp
from tools.checkout.db import init_app as _checkout_init_app
import tools.checkout.db as _checkout_db
from tools.system_locator.system_locator_app import systems_bp
from tools.system_locator.db import init_app as _system_locator_init_app
import tools.system_locator.db as _system_locator_db
from tools.print_requests.print_requests_app import print_requests_bp
from tools.print_requests.db import init_app as _print_requests_init_app
import tools.print_requests.db as _print_requests_db
from tools.api_v1.api_v1_app import api_v1_bp
from tools.admin.admin_app import admin_bp

app = Flask(__name__)

# --- Slice H, Issue #53: OpenAPI documentation via flasgger ---
# Guard with debug mode or explicit SWAGGER_ENABLED so the UI is not
# exposed in production by default.  The spec is always generated but
# the interactive Swagger UI is only mounted when the guard is active.
_SWAGGER_TEMPLATE = {
    "info": {
        "title": "Lab Tech Portal API",
        "description": (
            "JSON REST API for the Lab Tech Portal. "
            "Covers inventory, checkout, print requests, systems, and RF chambers."
        ),
        "version": "1.0.0",
        "contact": {"email": "lab-tech@alarm.com"},
    },
    "basePath": "/api/v1",
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "sessionAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "session",
            "description": "Okta SSO session cookie (set by /auth/callback)",
        }
    },
}

# --- Slice A, Issue #11: wire centralized config (fail-fast in production) ---
# load_config() reads FLASK_ENV and selects the matching config class.
# validate_config raises ValueError on misconfiguration in production.
# TestingConfig skips the strict checks (TESTING=True bypasses SECRET_KEY rule).
_cfg = _config.load_config()
try:
    _config.init_app(app, _cfg)
except ValueError as _cfg_err:  # pragma: no cover
    # Re-raise immediately so production/CI crashes loudly.
    # In testing, conftest sets config overrides after this import.
    import sys

    print(f"FATAL: {_cfg_err}", file=sys.stderr)
    raise

# --- Slice B, Issue #33: initialise structured logging ---
# Read from app.config (populated by config.init_app) so that test overrides
# and .env both flow through the single source of truth (pattern from PR #60).
init_logging(
    log_level=app.config.get("LOG_LEVEL", "INFO"),
    log_format=app.config.get("LOG_FORMAT", "plain"),
    structlog_enabled=app.config.get("STRUCTLOG_ENABLED", True),
)
_log = get_logger(__name__)

# --- Slice A, Issue #36: CSRF protection ---
csrf = CSRFProtect(app)

# --- Slice A, Issue #36: rate limiting ---
# Read from app.config (populated by config.init_app) so test overrides and
# .env both flow through a single source of truth.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[app.config["RATELIMIT_DEFAULT"]],
    storage_uri=app.config["RATELIMIT_STORAGE_URI"],
)

# --- Slice A, Issue #36: CORS for /api endpoints ---
# CORS_ORIGINS is a comma-separated list. Empty list means no cross-origin
# requests are permitted (the default — server-rendered HTML doesn't need CORS).
# Slice C's /api/v1/ endpoints rely on this knob.
_cors_origins = [o.strip() for o in app.config.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    from flask_cors import CORS

    CORS(app, resources={r"/api/*": {"origins": _cors_origins}}, supports_credentials=True)

# --- Slice C, Issue #12: graceful Redis degradation ---
# Ping Redis on startup; log a warning and continue if unreachable so that
# non-async features keep working without Redis in dev/CI.
def _check_redis() -> None:
    redis_url = app.config.get("REDIS_URL")
    if not redis_url:
        return
    try:
        import redis as _redis
        _redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
        _log.info("Redis reachable", url=redis_url)
    except Exception as _exc:  # noqa: BLE001
        _log.warning("Redis unreachable — async features disabled", error=str(_exc))

if not (app.testing or os.environ.get("TESTING") == "1"):
    _check_redis()

# --- Sprint 8, Issue #30: Flask-Session Redis backend ---
# _init_sessions() wires flask-session when SESSION_TYPE=redis.
# When SESSION_TYPE=cookie (the default), this is a no-op and Flask's built-in
# client-side cookie sessions are used unchanged (backward-compatible).
#
# F06 guard: Redis health-check is done once at init time, not per-request.
# F12 guard: SESSION_REDIS_URL and CELERY_BROKER_URL are separate config keys
#            pointing at different DB numbers (DB 1 vs DB 0).
def _redact_url_credentials(url: str) -> str:
    """Return a URL with the password component replaced by ``***`` for safe logging.

    Examples:
        redis://host:6379/1                 → redis://host:6379/1            (no userinfo)
        redis://user:pass@host:6379/1       → redis://user:***@host:6379/1
        redis://:pass@host:6379/1           → redis://:***@host:6379/1
    """
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


def _init_sessions(application: Flask) -> None:
    """Initialise flask-session with a Redis backend when SESSION_TYPE=redis.

    Must be called after ``config.init_app()`` has populated ``application.config``.
    In cookie mode (the default) this function is a no-op.
    """
    session_type = application.config.get("SESSION_TYPE", "cookie")
    if session_type != "redis":
        return

    import redis as _redis_lib
    from flask_session import Session as _FlaskSession
    from datetime import timedelta

    redis_url = application.config.get("SESSION_REDIS_URL", "redis://redis:6379/1")
    safe_url = _redact_url_credentials(redis_url)
    try:
        redis_client = _redis_lib.Redis.from_url(
            redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        redis_client.ping()
    except Exception as _exc:  # noqa: BLE001
        # F06: fail loudly on startup when Redis is required but unreachable.
        # Use the credential-redacted URL in the error message so secrets are
        # not leaked through logs or stack traces.
        raise RuntimeError(
            f"SESSION_TYPE=redis but Redis is unreachable at {safe_url}: {_exc}"
        ) from _exc

    lifetime_secs = application.config.get("SESSION_LIFETIME_SECONDS", 86400)
    application.config["SESSION_TYPE"] = "redis"
    application.config["SESSION_REDIS"] = redis_client
    application.config["SESSION_KEY_PREFIX"] = application.config.get(
        "SESSION_KEY_PREFIX", "lab-portal:session:"
    )
    application.config["SESSION_PERMANENT"] = True
    application.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=lifetime_secs)
    _FlaskSession(application)
    _log.info(
        "Flask-Session initialised with Redis backend",
        redis_url=safe_url,
        ttl_seconds=lifetime_secs,
    )


# --- Sprint 8, Issue #29: object storage initialisation ---
# _init_storage() reads OBJECT_STORAGE_BACKEND from app.config and attaches
# the chosen ObjectStorage implementation to app.config['OBJECT_STORAGE'].
# Called here (once at startup) so F06 — bucket-existence check in hot path —
# is honoured: the check runs at startup, not per-request.
def _init_storage(flask_app) -> None:
    """Construct the storage backend and attach it to app.config['OBJECT_STORAGE']."""
    try:
        storage = _object_storage_module.get_storage(flask_app.config)
        flask_app.config["OBJECT_STORAGE"] = storage
        _log.info(
            "Object storage initialised",
            backend=flask_app.config.get("OBJECT_STORAGE_BACKEND", "local"),
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("Object storage init failed — startup aborted", error=str(exc))
        raise


# Always initialise storage at startup. Previously this had a no-op test-mode
# branch that still called _init_storage, plus a check on `app.testing` which
# is False at import time (it flips to True only when a TestingConfig is
# applied). Tests that want a different backend replace
# app.config['OBJECT_STORAGE'] in their fixture; the default LocalFS init
# against DATA_DIR/uploads/ is harmless in test mode.
_init_storage(app)

if not os.environ.get("OKTA_ISSUER"):
    app.config["LOCAL_AUTH"] = True
    _log.warning("Okta not configured; falling back to local account login.")
app.register_blueprint(inventory_bp, url_prefix="/inventory")
app.register_blueprint(rf_chamber_bp, url_prefix="/rf-chamber")
app.register_blueprint(checkout_bp, url_prefix="/checkout")
app.register_blueprint(systems_bp, url_prefix="/systems")
app.register_blueprint(print_requests_bp, url_prefix="/print-requests")
app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
app.register_blueprint(admin_bp, url_prefix="/admin")
csrf.exempt(api_v1_bp)

# --- Slice H, Issue #53: mount Swagger UI at /api/v1/docs (dev/test only) ---
if app.debug or app.config.get("SWAGGER_ENABLED"):
    from flasgger import Swagger
    swagger = Swagger(
        app,
        template=_SWAGGER_TEMPLATE,
        config={
            "headers": [],
            "specs": [
                {
                    "endpoint": "api_v1_spec",
                    "route": "/api/v1/docs/openapi.json",
                    "rule_filter": lambda rule: rule.rule.startswith("/api/v1"),
                    "model_filter": lambda tag: True,
                }
            ],
            "static_url_path": "/api/v1/docs/static",
            "swagger_ui": True,
            "specs_route": "/api/v1/docs/",
        },
    )

_inventory_init_app(app)
_rf_chamber_init_app(app)
_checkout_init_app(app)
_system_locator_init_app(app)
_print_requests_init_app(app)
# Slice B, Issue #46: initialise the shared audit log DB.
_audit_log_module.init_app(app)
# Slice B, Issue #32: initialise Prometheus metrics (no-op when METRICS_ENABLED=False).
_metrics_module.init_app(app)

# Ensure RF chamber QR codes use a consistent host when configured.
app.config["RF_CHAMBER_BASE_URL"] = os.environ.get("RF_CHAMBER_BASE_URL", "")

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@app.after_request
def _apply_security_headers(response):
    """Inject security headers on every response (CSP + cookie flags in production).

    Slice A, Issue #36.
    """
    env = app.config.get("FLASK_ENV", "development")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class User(UserMixin):
    def __init__(self, email: str, display_name: str, username: str) -> None:
        self.id = email
        self.email = email
        self.display_name = display_name
        self.username = username


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    identity = session.get("user_identity")
    if not identity or identity.get("email") != user_id:
        return None
    return User(
        email=identity.get("email", ""),
        display_name=identity.get("display_name", identity.get("email", "")),
        username=identity.get("username", identity.get("email", "")),
    )


@login_manager.unauthorized_handler
def handle_unauthorized():
    return redirect(url_for("login", next=request.url))


@app.context_processor
def _inject_role_flags():
    """Expose ``is_admin`` to all templates so admin-only links can be hidden.

    Mirrors services.rbac: in LOCAL_AUTH mode every local user is treated
    as admin; otherwise the tier is derived from the Okta groups claim.
    """
    if current_app.config.get("LOGIN_DISABLED"):
        return {"is_admin": True}
    identity = session.get("user_identity") or {}
    if not identity:
        return {"is_admin": False}
    from services.rbac import get_user_tier

    return {"is_admin": get_user_tier(identity.get("groups", [])) == "admin"}


def _is_safe_redirect(target: str) -> bool:
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(target)
    if redirect_url.scheme and redirect_url.scheme != host_url.scheme:
        return False
    if redirect_url.netloc and redirect_url.netloc != host_url.netloc:
        return False
    return True


def _get_okta_service() -> OktaAuthService:
    service = current_app.config.get("OKTA_AUTH_SERVICE")
    if not service:
        service = OktaAuthService()
        current_app.config["OKTA_AUTH_SERVICE"] = service
    return service


# --- Slice B, Issue #7: liveness + readiness probes ---
# Registered before the before_request login gate and explicitly exempted in
# require_login() below so that Kubernetes / Docker HEALTHCHECK can reach
# these endpoints without a session cookie.
#
# Pattern: docs/patterns/observability/audit-logging.md
# (qe-architecture-ai-assisted-guide @ 81d85b9)


@app.route("/healthz")
def healthz():
    """Liveness probe — returns 200 unconditionally once the process is up."""
    return jsonify({"status": "ok"}), 200


def _check_db(label: str, db_path: str, timeout: float = 1.0) -> dict:
    """Run SELECT 1 against *db_path* with a short timeout.

    Returns a dict with ``status`` ("ok" or "error") and, on failure, a
    ``detail`` key describing the failure.  Uses a dedicated short-lived
    connection so a hung main-app connection cannot cause /readyz to block.

    Opens the DB via SQLite URI ``mode=rw`` so a missing file fails fast
    rather than being silently created (which would otherwise make the probe
    report green for a deleted/unmounted volume).

    Slice B, Issue #32: probe duration is recorded in the
    ``lab_portal_db_query_duration_seconds`` histogram (per-tool wrapping is
    deferred to Slice D-part2).
    """
    # Use the histogram as a context manager so duration is always recorded,
    # even on failure — the label is the DB name passed by the caller.
    with _metrics_module.db_query_duration_seconds.labels(db=label).time():
        try:
            # urllib quoting handles spaces / unusual chars in the path safely.
            uri = f"file:{_url_quote(db_path)}?mode=rw"
            conn = sqlite3.connect(uri, timeout=timeout, uri=True)
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
            return {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": str(exc)}


def _check_redis_readyz() -> dict | None:
    """Check Redis reachability via ping() with 1-second socket timeout.

    Returns None if REDIS_URL is not configured (no false negative — the check
    is omitted from /readyz when Redis is not in use).

    Returns a dict with ``status`` ("ok" or "error") and, on error, a
    ``detail`` key describing the failure.

    Slice D, Issue #89: observability enhancement for async degradation.
    """
    redis_url = current_app.config.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
        redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


@app.route("/readyz")
def readyz():
    """Readiness probe — checks every tool SQLite DB with SELECT 1 and Redis.

    Returns 200 with a per-check status map when all checks are healthy.
    Returns 503 with the same map (plus ``detail`` on failures) when any check
    is down.  Uses a 1 s per-check timeout so a hung resource never blocks the
    probe. The Redis check is omitted if REDIS_URL is not configured.
    """
    db_checks = {
        "inventory": _check_db("inventory", _inventory_db.DB_PATH),
        "rf_chamber": _check_db("rf_chamber", _rf_db.DB_PATH),
        "checkout": _check_db("checkout", _checkout_db.DB_PATH),
        "system_locator": _check_db("system_locator", _system_locator_db.DB_PATH),
        "print_requests": _check_db("print_requests", _print_requests_db.DB_PATH),
        "audit_log": _check_db("audit_log", _audit_log_module.DB_PATH),
    }
    checks = db_checks.copy()
    redis_check = _check_redis_readyz()
    if redis_check is not None:
        checks["redis"] = redis_check

    all_ok = all(v["status"] == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    body = {"status": "ok" if all_ok else "degraded", "checks": checks}
    return jsonify(body), status_code


# --- Slice B, Issue #33: request correlation middleware ---
# Extract / generate a request ID and bind it (plus user/path/method) into
# the structlog context so every log line in this request carries those fields.


@app.before_request
def _bind_request_logging():
    """Stash request_id, path, method, user_email in structlog context."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.environ["REQUEST_ID"] = request_id
    user_email = None
    if current_user.is_authenticated:
        user_email = getattr(current_user, "email", None)
    bind_request_context(
        request_id=request_id,
        path=request.path,
        method=request.method,
        user_email=user_email,
    )
    request.environ["_request_start_time"] = time.monotonic()


@app.after_request
def _log_request(response):
    """Emit a single structured log line per request with status + duration.

    Also echoes the request's correlation ID back to the client via the
    ``X-Request-ID`` response header so callers (and downstream services
    in Sprint 3 onward) can stitch their traces to the server log line.
    """
    duration_ms = round(
        (time.monotonic() - request.environ.get("_request_start_time", time.monotonic())) * 1000,
        1,
    )
    request_id = request.environ.get("REQUEST_ID")
    if request_id:
        response.headers["X-Request-ID"] = request_id
    _log.info(
        "request",
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.teardown_request
def _clear_request_logging(_exc=None):
    """Clear per-request structlog context after the response is sent."""
    clear_request_context()


@app.before_request
def require_login():
    if current_app.config.get("LOGIN_DISABLED"):
        return None
    if not request.endpoint:
        return None
    if request.endpoint.startswith("static"):
        return None
    if request.endpoint in {"login", "local_login", "register", "auth_callback", "logout", "healthz", "readyz", "metrics", "prometheus_metrics"}:
        return None
    # api_v1 blueprint handles its own auth and returns 401 JSON (not 302).
    # Exclude it here so unauthenticated API callers get JSON, not a redirect.
    if request.endpoint.startswith("api_v1."):
        return None
    # Swagger UI and spec endpoints are read-only and acceptable unauthenticated
    # in dev/debug mode (SWAGGER_ENABLED guard in Swagger init above).
    if request.path.startswith("/api/v1/docs"):
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=request.url))
    return None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/resources")
def resources():
    resource_links = [
        {
            "title": "QE Lab Tech Management Overview",
            "description": "Role charter outlining responsibilities, tooling, and collaboration touchpoints.",
            "url": "https://confluence.corp.adcinternal.com/display/QE/QE+Lab+Tech+Management",
        },
        {
            "title": "Lab Request Ticket Guide",
            "description": "Step-by-step instructions for opening Lab Request work items in Jira.",
            "url": "https://confluence.corp.adcinternal.com/display/RM/Lab+Request+ticket+-+How+to+create",
        },
    ]
    return render_template("resources.html", resource_links=resource_links)


@app.route("/login")
def login():
    if current_app.config.get("LOCAL_AUTH"):
        next_url = request.args.get("next", "")
        return render_template("login.html", next=next_url, error=None, username=None)
    try:
        okta = _get_okta_service()
    except OktaAuthError as exc:
        return f"Okta configuration error: {exc}", 500
    next_url = request.args.get("next")
    if next_url and _is_safe_redirect(next_url):
        session["post_login_redirect"] = next_url
    state = okta.new_state()
    nonce = okta.new_nonce()
    session["okta_state"] = state
    session["okta_nonce"] = nonce
    return redirect(okta.get_authorization_url(state=state, nonce=nonce))


@app.route("/local-login", methods=["POST"])
def local_login():
    if not current_app.config.get("LOCAL_AUTH"):
        return redirect(url_for("login"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")
    account = verify_local_user(username, password)
    if not account:
        return render_template("login.html", error="Invalid username or password.",
                               next=next_url, username=username)
    session["user_identity"] = {
        "email": account["email"],
        "display_name": account["display_name"],
        "username": account["username"],
        "groups": ["admin"],
    }
    login_user(User(
        email=account["email"],
        display_name=account["display_name"],
        username=account["username"],
    ))
    if next_url and _is_safe_redirect(next_url):
        return redirect(next_url)
    return redirect(url_for("home"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config.get("LOCAL_AUTH"):
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("register.html", error=None, form={})
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    form = {"username": username, "display_name": display_name, "email": email}
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.", form=form)
    error = create_local_user(username, display_name, email, password)
    if error:
        return render_template("register.html", error=error, form=form)
    account = verify_local_user(username, password)
    session["user_identity"] = {
        "email": account["email"],
        "display_name": account["display_name"],
        "username": account["username"],
        "groups": ["admin"],
    }
    login_user(User(
        email=account["email"],
        display_name=account["display_name"],
        username=account["username"],
    ))
    return redirect(url_for("home"))


@app.route("/auth/callback")
def auth_callback():
    if request.args.get("error"):
        return (
            f"Okta authentication failed: {request.args.get('error_description', 'Unknown error')}",
            401,
        )

    state = request.args.get("state")
    if not state or state != session.get("okta_state"):
        return "Invalid authentication state.", 400

    code = request.args.get("code")
    if not code:
        return "Missing authorization code.", 400

    try:
        okta = _get_okta_service()
        tokens = okta.exchange_code_for_tokens(code)
        claims = okta.verify_id_token(tokens["id_token"], nonce=session.get("okta_nonce"))
        identity = okta.extract_identity(claims)
    except OktaAuthError as exc:
        return f"Okta authentication failed: {exc}", 401

    session["user_identity"] = identity
    session["id_token"] = tokens.get("id_token")
    session.pop("okta_state", None)
    session.pop("okta_nonce", None)

    # `identity` carries a `groups` key (used by services/rbac.py via the
    # session payload above); `User` only consumes the three identity fields.
    login_user(User(
        email=identity["email"],
        display_name=identity["display_name"],
        username=identity["username"],
    ))
    # Slice B, Issue #32: track active sessions (resets on process restart).
    _metrics_module.active_user_sessions.inc()

    redirect_target = session.pop("post_login_redirect", None)
    if redirect_target and _is_safe_redirect(redirect_target):
        return redirect(redirect_target)
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    id_token = session.get("id_token")
    logout_user()
    session.clear()
    # Slice B, Issue #32: decrement active session count on logout.
    # The gauge may briefly go below 0 after a process restart (in-memory state
    # resets to 0 while clients still hold valid sessions). This is an accepted
    # limitation documented in services/metrics.py.
    _metrics_module.active_user_sessions.dec()

    post_logout_redirect = url_for("home", _external=True)
    try:
        okta = _get_okta_service()
        logout_url = okta.get_logout_url(
            id_token=id_token,
            post_logout_redirect=post_logout_redirect,
        )
    except OktaAuthError:
        logout_url = None

    if logout_url:
        return redirect(logout_url)
    return redirect(url_for("home"))

# --- Slice D, Issue #35: audit log route moved to tools/api_v1/api_v1_app.py ---
# URL /api/v1/audit-log is preserved; served by the api_v1 blueprint.


# ---------------------------------------------------------------------------
# Global error handlers — Slice C, Issue #34
# Content-negotiate: JSON for /api/* paths, HTML for browser requests.
# request_id is included in every error payload/page for log correlation.
# ---------------------------------------------------------------------------


def _is_api_request() -> bool:
    """Return True when the request is for an /api/* path."""
    return request.path.startswith("/api/")


def _get_request_id() -> str:
    """Return the current request's correlation ID.

    Normally set by _bind_request_logging() in the before_request hook.
    Flask-WTF (CSRF) and Flask-Limiter (429) register their own before_request
    handlers and can raise errors *before* _bind_request_logging() runs.  In
    that case we generate-and-store a UUID so every error path emits a usable
    request_id rather than an empty string.
    """
    rid = request.environ.get("REQUEST_ID")
    if not rid:
        rid = str(uuid.uuid4())
        request.environ["REQUEST_ID"] = rid
    return rid


@app.errorhandler(404)
def not_found(e):
    """404 handler: JSON for API paths, HTML for browser requests."""
    request_id = _get_request_id()
    _log.error("404 Not Found", path=request.path, request_id=request_id)
    if _is_api_request():
        return jsonify({"error": "Not found", "request_id": request_id, "status": 404}), 404
    return render_template("errors/404.html", request_id=request_id), 404


@app.errorhandler(500)
def internal_server_error(e):
    """500 handler: JSON for API paths, HTML for browser requests. Never exposes stack traces."""
    request_id = _get_request_id()
    _log.error("500 Internal Server Error", path=request.path, request_id=request_id, exc_info=e)
    if _is_api_request():
        return (
            jsonify({"error": "Internal server error", "request_id": request_id, "status": 500}),
            500,
        )
    return render_template("errors/500.html", request_id=request_id), 500


@app.errorhandler(429)
def rate_limit_exceeded(e):
    """429 handler: structured rate-limit response matching global error format."""
    request_id = _get_request_id()
    _log.error("429 Rate Limit Exceeded", path=request.path, request_id=request_id)
    if _is_api_request():
        return (
            jsonify({"error": "Rate limit exceeded", "request_id": request_id, "status": 429}),
            429,
        )
    return render_template("errors/429.html", request_id=request_id), 429


@app.errorhandler(CSRFError)
def csrf_error(e):
    """CSRF error handler: 400 with structured response."""
    request_id = _get_request_id()
    _log.error("400 CSRF validation failed", path=request.path, request_id=request_id)
    if _is_api_request():
        return (
            jsonify({"error": "CSRF validation failed", "request_id": request_id, "status": 400}),
            400,
        )
    return render_template("errors/400.html", request_id=request_id), 400
# --- Slice C, Issue #13: Celery instance exported for workers ---
# celery_app.py is a pure factory; the module-level instance lives here so
# workers use ``celery -A app worker/beat`` without circular imports.
celery = make_celery(app)


if __name__ == "__main__":
    app.run(debug=True)