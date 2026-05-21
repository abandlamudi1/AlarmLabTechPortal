import sqlite3

import pytest

from app import app as flask_app
from tools.inventory import db as inventory_db
from tools.rf_chamber import db as rf_db
from tools.system_locator import db as systems_db
from tools.print_requests import db as print_requests_db
from tools.checkout import db as checkout_db
import services.audit_log as audit_log_module
from services.object_storage import LocalFilesystemStorage


@pytest.fixture
def app(tmp_path, monkeypatch):
    # --- DATA_DIR sub-directories (Slice D-part1, #2) ---
    data_dir = tmp_path / "data"
    db_dir = data_dir / "db"
    generated_dir = data_dir / "generated" / "inventory"
    upload_dir = data_dir / "uploads"
    db_dir.mkdir(parents=True)
    generated_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)

    # --- Wire DATA_DIR into app config so _ensure_upload_folder and _qr_dir
    #     resolve paths under tmp_path rather than the developer's home dir. ---
    flask_app.config["DATA_DIR"] = str(data_dir)

    # --- Per-tool DB path overrides (keeps tests isolated from any real DBs) ---
    inv_db_path = db_dir / "inventory.db"
    rf_db_path = db_dir / "rf_chambers.db"
    system_db_path = db_dir / "systems.db"
    print_db_path = db_dir / "print_requests.db"

    monkeypatch.setattr(inventory_db, "DB_PATH", str(inv_db_path))
    inventory_db.init_db()
    with sqlite3.connect(inv_db_path) as conn:
        conn.execute("DELETE FROM items")
        conn.execute(
            "INSERT INTO items (name, description, quantity, min_stock, qr_code) VALUES (?, ?, ?, ?, ?)",
            ("Spectrum Analyzer", "Keysight SA", 5, 2, None),
        )

    monkeypatch.setattr(rf_db, "DB_PATH", str(rf_db_path))
    rf_db.init_db()
    with sqlite3.connect(rf_db_path) as conn:
        conn.execute("DELETE FROM chambers")
        conn.execute(
            "INSERT INTO chambers (barcode, size, ports, purpose, location, owner) VALUES (?, ?, ?, ?, ?, ?)",
            ("XL001", "Large", "Ethernet Port", "EMI Testing", "Bay 3", "Alex"),
        )

    monkeypatch.setattr(systems_db, "DB_PATH", str(system_db_path))
    systems_db.init_db()
    with sqlite3.connect(system_db_path) as conn:
        conn.execute("DELETE FROM identifiers")
        conn.execute("DELETE FROM systems")

    monkeypatch.setattr(print_requests_db, "DB_PATH", str(print_db_path))
    print_requests_db.init_db()
    flask_app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(upload_dir)
    flask_app.config["PRINT_REQUESTS_CREATE_JIRA"] = False

    checkout_db_path = db_dir / "checkout.db"
    monkeypatch.setattr(checkout_db, "DB_PATH", str(checkout_db_path))
    checkout_db.init_db()

    audit_db_path = db_dir / "audit.db"
    monkeypatch.setattr(audit_log_module, "DB_PATH", str(audit_db_path))
    audit_log_module.init_db()

    flask_app.config.update(
        TESTING=True,
        RF_CHAMBER_BASE_URL="",
        LOGIN_DISABLED=True,
        # Disable CSRF in the test environment so form posts don't need tokens.
        # Individual tests that exercise CSRF behaviour set WTF_CSRF_ENABLED=True
        # explicitly and generate a valid token via the test client session.
        WTF_CSRF_ENABLED=False,
        # PIN used by existing test_pin_protected_delete tests (test fixture value).
        SYSTEM_LOCATOR_DELETE_PIN="9420",
        # Disable Prometheus metrics by default. METRICS_ENABLED=False causes
        # init_app() to return early without registering additional routes, which
        # prevents ValueError from re-registering metrics across test runs.
        # Note: the /metrics route may already be present on the shared app
        # singleton from import-time registration (see test_metrics.py for docs
        # on that known behaviour). Individual test_metrics.py tests that need
        # a live /metrics endpoint set METRICS_ENABLED=True and call init_app.
        METRICS_ENABLED=False,
        # Sprint 8, Issue #29: default all tests to LocalFilesystemStorage so
        # boto3 / real S3 calls never happen in the test suite.
        OBJECT_STORAGE_BACKEND="local",
    )
    # Wire a fresh LocalFilesystemStorage rooted at upload_dir for this test.
    # Tests that need a different backend can replace app.config['OBJECT_STORAGE'].
    flask_app.config["OBJECT_STORAGE"] = LocalFilesystemStorage(root_dir=str(upload_dir))
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Sprint 8 Issue #30: Redis session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def redis_client():
    """Yield a fakeredis instance for Redis-backed session tests.

    Uses fakeredis so tests run without a real Redis server. The instance is
    flushed and closed after each test to ensure isolation.
    """
    import fakeredis
    client = fakeredis.FakeRedis()
    yield client
    client.flushall()
    client.close()


@pytest.fixture
def redis_app(redis_client):
    """Flask app instance wired to fakeredis for session-storage testing.

    SESSION_TYPE=redis with a fakeredis backend so tests verify that sessions
    are written to / read from Redis without requiring a live Redis process.
    """
    from flask import Flask, session
    from flask_session import Session as _FlaskSession
    from datetime import timedelta
    import uuid

    app = Flask(f"test_redis_sessions_{uuid.uuid4().hex[:6]}")
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        SESSION_TYPE="redis",
        SESSION_REDIS=redis_client,
        SESSION_KEY_PREFIX="lab-portal:session:",
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=3600),
        WTF_CSRF_ENABLED=False,
    )
    _FlaskSession(app)

    @app.route("/set")
    def set_session():
        session["user_identity"] = {"email": "user@example.com", "groups": ["Lab-Techs"]}
        session.modified = True
        return "ok"

    @app.route("/get")
    def get_session():
        val = session.get("user_identity")
        return val["email"] if val else "none"

    @app.route("/clear")
    def clear_session():
        session.clear()
        return "cleared"

    return app
