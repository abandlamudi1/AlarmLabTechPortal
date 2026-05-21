"""Tests for config.py validation and init_app wiring (Slice A, Issue #11)."""
from __future__ import annotations

import pytest

import config as cfg_module
from config import (
    BaseConfig,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    init_app,
    load_config,
    validate_config,
)


# ---------------------------------------------------------------------------
# validate_config unit tests
# ---------------------------------------------------------------------------


def test_validate_config_passes_for_dev():
    """Development config with no secrets set should have no validation errors."""
    cfg = DevelopmentConfig()
    errors = validate_config(cfg)
    assert errors == []


def test_validate_config_fails_in_production_with_default_secret(monkeypatch):
    """Production with SECRET_KEY='change-me' must return an error."""
    monkeypatch.setenv("SECRET_KEY", "change-me")
    monkeypatch.setenv("FLASK_ENV", "production")
    cfg = ProductionConfig()
    errors = validate_config(cfg)
    assert any("SECRET_KEY" in e for e in errors)


def test_validate_config_passes_in_production_with_real_secret(monkeypatch):
    """Production with a strong SECRET_KEY should pass."""
    monkeypatch.setenv("SECRET_KEY", "super-secure-random-value-xyz-123")
    monkeypatch.setenv("FLASK_ENV", "production")
    # Ensure no partial-Okta or JIRA-PAT-without-URL errors from developer env
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OKTA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OKTA_ISSUER", raising=False)
    monkeypatch.delenv("OKTA_REDIRECT_URI", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)
    cfg = ProductionConfig()
    errors = validate_config(cfg)
    assert errors == []


def test_validate_config_fails_with_partial_okta(monkeypatch):
    """Partial Okta config (only OKTA_CLIENT_ID set) must return an error."""
    monkeypatch.setenv("OKTA_CLIENT_ID", "0oa123")
    monkeypatch.setenv("OKTA_CLIENT_SECRET", "")
    monkeypatch.setenv("OKTA_ISSUER", "")
    monkeypatch.setenv("OKTA_REDIRECT_URI", "")
    cfg = DevelopmentConfig()
    errors = validate_config(cfg)
    assert any("Okta" in e for e in errors)


def test_validate_config_fails_with_jira_pat_no_url_in_production(monkeypatch):
    """JIRA_PAT set without JIRA_URL must return an error in production."""
    monkeypatch.setenv("JIRA_PAT", "my-token")
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "super-secure-random-value-xyz-123")
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OKTA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OKTA_ISSUER", raising=False)
    monkeypatch.delenv("OKTA_REDIRECT_URI", raising=False)
    cfg = ProductionConfig()
    errors = validate_config(cfg)
    assert any("JIRA_PAT" in e for e in errors)


def test_validate_config_invalid_log_level(monkeypatch):
    """Invalid LOG_LEVEL must return an error."""
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    cfg = DevelopmentConfig()
    errors = validate_config(cfg)
    assert any("LOG_LEVEL" in e for e in errors)


# ---------------------------------------------------------------------------
# init_app fail-fast tests
# ---------------------------------------------------------------------------


def test_init_app_raises_in_production_with_bad_secret(monkeypatch):
    """init_app must raise ValueError when production SECRET_KEY is 'change-me'."""
    from flask import Flask

    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me")
    # Clear anything that might trigger unrelated validation errors
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OKTA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OKTA_ISSUER", raising=False)
    monkeypatch.delenv("OKTA_REDIRECT_URI", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)

    test_app = Flask(__name__)
    cfg = ProductionConfig()
    with pytest.raises(ValueError, match="Invalid configuration"):
        init_app(test_app, cfg)


def test_init_app_succeeds_in_dev_with_defaults(monkeypatch):
    """init_app must not raise in development with default env."""
    from flask import Flask

    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("JIRA_PAT", raising=False)
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)

    app = Flask(__name__)
    cfg = DevelopmentConfig()
    result = init_app(app, cfg)
    assert result is cfg
    assert app.config["FLASK_ENV"] == "development"


def test_init_app_populates_app_config(monkeypatch, tmp_path):
    """init_app must push all config fields into app.config."""
    from flask import Flask

    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = Flask(__name__)
    cfg = DevelopmentConfig()
    init_app(app, cfg)
    assert "SECRET_KEY" in app.config
    assert app.config["DATA_DIR"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Sprint 6 Issue #90: Celery worker tuning — config field defaults
# ---------------------------------------------------------------------------


def test_celery_worker_concurrency_default(monkeypatch):
    """CELERY_WORKER_CONCURRENCY defaults to os.cpu_count() or 2."""
    import os

    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)
    cfg = DevelopmentConfig()
    expected = os.cpu_count() or 2
    assert cfg.CELERY_WORKER_CONCURRENCY == expected


def test_celery_worker_concurrency_env_override(monkeypatch):
    """CELERY_WORKER_CONCURRENCY reads the env var when set."""
    monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "8")
    cfg = DevelopmentConfig()
    assert cfg.CELERY_WORKER_CONCURRENCY == 8


def test_celery_queues_default(monkeypatch):
    """CELERY_QUEUES defaults to 'celery' when not set."""
    monkeypatch.delenv("CELERY_QUEUES", raising=False)
    cfg = DevelopmentConfig()
    assert cfg.CELERY_QUEUES == "celery"


def test_celery_queues_env_override(monkeypatch):
    """CELERY_QUEUES reads the env var when set."""
    monkeypatch.setenv("CELERY_QUEUES", "high,default,low")
    cfg = DevelopmentConfig()
    assert cfg.CELERY_QUEUES == "high,default,low"


def test_worker_prefetch_multiplier_default(monkeypatch):
    """WORKER_PREFETCH_MULTIPLIER defaults to 1 (fair task distribution)."""
    monkeypatch.delenv("WORKER_PREFETCH_MULTIPLIER", raising=False)
    cfg = DevelopmentConfig()
    assert cfg.WORKER_PREFETCH_MULTIPLIER == 1


def test_result_expires_default(monkeypatch):
    """RESULT_EXPIRES defaults to 86400 seconds (1 day)."""
    monkeypatch.delenv("RESULT_EXPIRES", raising=False)
    cfg = DevelopmentConfig()
    assert cfg.RESULT_EXPIRES == 86400


def test_result_expires_env_override(monkeypatch):
    """RESULT_EXPIRES reads RESULT_EXPIRES env var when set."""
    monkeypatch.setenv("RESULT_EXPIRES", "3600")
    cfg = DevelopmentConfig()
    assert cfg.RESULT_EXPIRES == 3600


# ---------------------------------------------------------------------------
# Sprint 6 Issue #90: make_celery() conf propagation tests
# ---------------------------------------------------------------------------


def test_make_celery_propagates_tuning_settings(monkeypatch, tmp_path):
    """make_celery() must apply task_acks_late, prefetch, result_expires to celery.conf."""
    from flask import Flask

    from celery_app import make_celery

    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")

    app = Flask(__name__)
    cfg = DevelopmentConfig()
    init_app(app, cfg)

    celery = make_celery(app)

    assert celery.conf.task_acks_late is True
    assert celery.conf.worker_prefetch_multiplier == 1
    assert celery.conf.result_expires == 86400


def test_make_celery_include_lists_all_task_modules(monkeypatch, tmp_path):
    """make_celery() include= must list all three task modules."""
    from flask import Flask

    from celery_app import make_celery

    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OKTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")

    app = Flask(__name__)
    cfg = DevelopmentConfig()
    init_app(app, cfg)

    celery = make_celery(app)

    assert "tasks.print_request_tasks" in celery.conf.include
    assert "tasks.system_locator_tasks" in celery.conf.include
    assert "tasks.periodic" in celery.conf.include
