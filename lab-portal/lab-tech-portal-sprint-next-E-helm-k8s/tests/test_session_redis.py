"""Tests for Sprint 8 Issue #30: Flask-Session Redis backend.

Verifies:
  - SESSION_TYPE=cookie (default) — sessions stored in Flask cookie; no Redis
  - SESSION_TYPE=redis — sessions stored under the key prefix in Redis
  - Session TTL is respected (key expires after SESSION_LIFETIME_SECONDS)
  - Sessions shared across two test_client() instances when Redis-backed
  - Auth flow (session["user_identity"]) works in cookie mode (unchanged)
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest
from flask import Flask, session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cookie_app() -> Flask:
    """Minimal Flask app using the default cookie-based sessions."""
    app = Flask(f"test_cookie_sessions_{uuid.uuid4().hex[:6]}")
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        SESSION_TYPE="cookie",  # explicit default
        WTF_CSRF_ENABLED=False,
    )

    @app.route("/set")
    def set_session():
        session["user_identity"] = {"email": "user@example.com", "groups": ["Lab-Techs"]}
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


def _make_redis_app(redis_client: fakeredis.FakeRedis, ttl: int = 3600) -> Flask:
    """Minimal Flask app wired to a fakeredis instance for session storage."""
    from flask_session import Session as _FlaskSession
    from datetime import timedelta

    app = Flask(f"test_redis_sessions_{uuid.uuid4().hex[:6]}")
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        SESSION_TYPE="redis",
        SESSION_REDIS=redis_client,
        SESSION_KEY_PREFIX="lab-portal:session:",
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=ttl),
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# NOTE: `redis_client` and `redis_app` fixtures live in tests/conftest.py so
# they are shared across this module and any future Redis-backed test files.
# Do NOT redefine them locally — having two definitions with the same name
# silently diverged in an earlier draft of this PR (see Copilot round-1 review).
# The module-local helper `_make_redis_app(redis_client, ttl)` above remains —
# it is used by the TTL test below which needs a parameterized lifetime.


# ---------------------------------------------------------------------------
# Tests: cookie mode (default, backward-compatible)
# ---------------------------------------------------------------------------

class TestCookieMode:
    """SESSION_TYPE=cookie — Flask default behaviour, no Redis involved."""

    def test_session_stored_in_cookie(self):
        """Session data round-trips through the cookie without Redis."""
        app = _make_cookie_app()
        client = app.test_client()

        resp = client.get("/set")
        assert resp.status_code == 200

        # Cookie should be set in the response headers (Flask session cookie)
        assert "Set-Cookie" in resp.headers

        resp = client.get("/get")
        assert resp.data == b"user@example.com"

    def test_cookie_session_cleared(self):
        """Clearing the session removes the user_identity key."""
        app = _make_cookie_app()
        client = app.test_client()

        client.get("/set")
        assert client.get("/get").data == b"user@example.com"

        client.get("/clear")
        assert client.get("/get").data == b"none"

    def test_cookie_mode_auth_flow(self):
        """Simulate the auth callback session writes used in app.py."""
        app = _make_cookie_app()

        @app.route("/simulate-auth")
        def simulate_auth():
            session["user_identity"] = {
                "email": "tester@alarm.com",
                "display_name": "Test User",
                "username": "tester",
                "groups": ["Lab-Techs"],
            }
            session["id_token"] = "fake-id-token"
            return "ok"

        client = app.test_client()
        client.get("/simulate-auth")

        resp = client.get("/get")
        assert resp.data == b"tester@alarm.com"


# ---------------------------------------------------------------------------
# Tests: Redis mode
# ---------------------------------------------------------------------------

class TestRedisMode:
    """SESSION_TYPE=redis — sessions stored in fakeredis under key prefix."""

    def test_session_stored_in_redis(self, redis_app, redis_client):
        """After a request, a session key exists in Redis under the prefix."""
        client = redis_app.test_client()

        resp = client.get("/set")
        assert resp.status_code == 200

        keys = redis_client.keys("lab-portal:session:*")
        assert len(keys) >= 1, "Expected at least one session key in Redis"

    def test_session_data_readable_across_requests(self, redis_app):
        """Session data persists across multiple requests within the same client."""
        client = redis_app.test_client()
        client.get("/set")

        resp = client.get("/get")
        assert resp.data == b"user@example.com"

    def test_session_cleared_removes_redis_key(self, redis_app, redis_client):
        """Clearing the session empties or removes the specific session key.

        Note: Flask-Session's behavior on session.clear() differs across versions
        and backends — some implementations DELETE the Redis key, others overwrite
        it with an empty serialized session and let TTL expire it. We assert on
        the SPECIFIC key created by /set rather than `len(keys) == 0` so the test
        is robust to either implementation.
        """
        client = redis_app.test_client()
        client.get("/set")

        keys_before = redis_client.keys("lab-portal:session:*")
        assert len(keys_before) >= 1, "Session key should exist after /set"
        target_key = keys_before[0]
        value_before = redis_client.get(target_key)
        assert value_before, "Session key should have non-empty value after /set"

        client.get("/clear")

        # After clear, the target key is either deleted entirely OR its value
        # no longer encodes a user_identity. Both states are acceptable; what
        # would NOT be acceptable is the key still containing the cleared
        # session data.
        value_after = redis_client.get(target_key)
        if value_after is None:
            # Implementation A: key deleted. Acceptable.
            pass
        else:
            # Implementation B: key still present but session payload reset.
            # The serialized blob should NOT contain the user_identity payload.
            assert b"user_identity" not in value_after, (
                "After /clear, Redis still encodes user_identity — session not properly cleared"
            )

    def test_session_ttl_applied_by_flask_session(self, redis_client):
        """Flask-Session applies PERMANENT_SESSION_LIFETIME as the Redis TTL.

        We assert that the TTL Redis reports for the session key is within a
        narrow window of the configured lifetime. Forcing expiration via
        `pexpire` (the prior test) would have passed regardless of whether
        Flask-Session set any TTL at all, so it didn't actually validate the
        config. Here we read the live TTL and compare against the configured
        value — that's the property we care about.
        """
        configured_ttl = 120  # seconds — long enough that timing slop is irrelevant
        app = _make_redis_app(redis_client, ttl=configured_ttl)
        client = app.test_client()

        client.get("/set")
        keys = redis_client.keys("lab-portal:session:*")
        assert len(keys) >= 1, "Session should exist immediately after /set"

        # Redis TTL command returns the remaining time in seconds, -1 if no TTL,
        # -2 if the key doesn't exist. We accept anything in [configured-5, configured]
        # to allow for the tiny round-trip delay between SET and TTL.
        observed_ttl = redis_client.ttl(keys[0])
        assert observed_ttl > 0, (
            f"Redis reports no TTL ({observed_ttl}) on the session key — "
            f"PERMANENT_SESSION_LIFETIME={configured_ttl}s was not applied by Flask-Session"
        )
        assert configured_ttl - 5 <= observed_ttl <= configured_ttl, (
            f"Observed TTL {observed_ttl}s is outside expected window "
            f"[{configured_ttl - 5}, {configured_ttl}] for configured lifetime"
        )

    def test_sessions_shared_across_two_clients(self, redis_app):
        """Two test clients sharing the same Redis see each other's sessions.

        Mirrors the multi-replica scenario: client_a writes a session; we lift
        the session cookie from the Flask test client's cookie jar (not by
        string-splitting the Set-Cookie header — that's brittle if multiple
        Set-Cookie headers, different attribute orderings, or other cookies
        are present) and replay it into client_b. client_b then reads the
        session from the shared Redis backend.
        """
        client_a = redis_app.test_client()
        client_b = redis_app.test_client()

        # client_a writes a session
        resp_a = client_a.get("/set")
        assert resp_a.status_code == 200

        # Parse the response's Set-Cookie headers with the stdlib SimpleCookie
        # parser rather than splitting on ';' (which mishandles multi-cookie
        # responses, attribute ordering, and quoted values). SimpleCookie is in
        # the stdlib and stable across Werkzeug versions, unlike the test
        # client's internal `_cookies` jar.
        from http.cookies import SimpleCookie

        parsed = SimpleCookie()
        for set_cookie in resp_a.headers.get_all("Set-Cookie"):
            parsed.load(set_cookie)
        assert "session" in parsed, "client_a response should include a 'session' Set-Cookie"
        session_cookie_value = parsed["session"].value

        # Replay the cookie into client_b so subsequent requests carry the same
        # session ID. Flask-Session resolves the cookie → Redis key → data.
        client_b.set_cookie("session", session_cookie_value)

        # client_b should now read the session data written by client_a
        resp_b = client_b.get("/get")
        assert resp_b.data == b"user@example.com", (
            "client_b should read session data written by client_a via shared Redis"
        )

    def test_redis_key_prefix_namespace(self, redis_app, redis_client):
        """All session keys are namespaced under 'lab-portal:session:'."""
        client = redis_app.test_client()
        client.get("/set")

        all_keys = redis_client.keys("*")
        for key in all_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            assert key_str.startswith("lab-portal:session:"), (
                f"Unexpected Redis key outside namespace: {key_str}"
            )


# ---------------------------------------------------------------------------
# Tests: _init_sessions helper (integration with app factory)
# ---------------------------------------------------------------------------

class TestInitSessionsHelper:
    """Verify the _init_sessions() helper in app.py behaves correctly."""

    def test_cookie_mode_noop(self):
        """_init_sessions() with SESSION_TYPE=cookie does nothing (no import of flask_session)."""
        from app import _init_sessions

        mini = Flask(f"test_init_noop_{uuid.uuid4().hex[:6]}")
        mini.config["SESSION_TYPE"] = "cookie"
        # Should not raise; flask_session is not wired
        _init_sessions(mini)
        # No SESSION_REDIS key should be set
        assert "SESSION_REDIS" not in mini.config

    def test_redis_mode_wires_flask_session(self, redis_client):
        """_init_sessions() with SESSION_TYPE=redis wires flask-session correctly."""
        from app import _init_sessions

        mini = Flask(f"test_init_redis_{uuid.uuid4().hex[:6]}")
        mini.config.update(
            SECRET_KEY="test",
            TESTING=True,
            SESSION_TYPE="redis",
            SESSION_REDIS_URL="redis://localhost:6379/1",
            SESSION_LIFETIME_SECONDS=3600,
            SESSION_KEY_PREFIX="lab-portal:session:",
        )

        # Patch the redis client so we don't need a real Redis server
        import redis as redis_lib
        import unittest.mock as mock

        with mock.patch.object(redis_lib.Redis, "from_url", return_value=redis_client):
            _init_sessions(mini)

        # flask-session should have been configured
        assert mini.config.get("SESSION_TYPE") == "redis"
        assert mini.config.get("SESSION_REDIS") is redis_client
