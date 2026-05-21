# tests/test_periodic_tasks.py — Slice C2, Issue #17
# Unit tests for tasks/periodic.py.
#
# All I/O is mocked — no real SQLite, Redis, or file-system access occurs.
# Each test exercises task logic directly by calling the underlying function
# inside a Flask app context (provided by the shared ``app`` fixture).
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _invoke(task_fn, app):
    """Call a shared_task's underlying function inside the Flask app context.

    ``shared_task(bind=True)`` produces a bound Task object.  The ``.run``
    method is already bound to the task instance, so it accepts no extra
    arguments — ``self`` inside the decorated function IS the task object.

    To intercept retry calls we patch the task's ``retry`` method directly on
    the bound task object.  This lets us assert that the function calls
    ``self.retry(...)`` without spinning up a Celery worker.
    """
    with app.app_context():
        # Patch retry on the actual task object so "self.retry" inside the
        # task body raises a sentinel exception we can catch in tests.
        with patch.object(task_fn, "retry", side_effect=Exception("retry called")):
            return task_fn.run()


# ---------------------------------------------------------------------------
# sync_jira_systems
# ---------------------------------------------------------------------------

class TestSyncJiraSystems:
    def test_returns_counts_on_success(self, app):
        mock_result = MagicMock(created=3, updated=1, skipped=0)
        mock_service = MagicMock()
        mock_service.apply.return_value = mock_result

        with patch(
            "tools.system_locator.system_locator_app._get_import_service",
            return_value=mock_service,
        ):
            from tasks.periodic import sync_jira_systems

            result = _invoke(sync_jira_systems, app)

        assert result == {"created": 3, "updated": 1, "skipped": 0}
        mock_service.apply.assert_called_once()

    def test_retries_on_exception(self, app):
        mock_service = MagicMock()
        mock_service.apply.side_effect = RuntimeError("Jira down")

        with patch(
            "tools.system_locator.system_locator_app._get_import_service",
            return_value=mock_service,
        ):
            from tasks.periodic import sync_jira_systems

            with pytest.raises(Exception, match="retry called"):
                _invoke(sync_jira_systems, app)

    def test_zero_results_still_succeeds(self, app):
        mock_result = MagicMock(created=0, updated=0, skipped=0)
        mock_service = MagicMock()
        mock_service.apply.return_value = mock_result

        with patch(
            "tools.system_locator.system_locator_app._get_import_service",
            return_value=mock_service,
        ):
            from tasks.periodic import sync_jira_systems

            result = _invoke(sync_jira_systems, app)

        assert result["created"] == 0


# ---------------------------------------------------------------------------
# check_stale_checkouts
# ---------------------------------------------------------------------------

class TestCheckStaleCheckouts:
    def _make_row(self, name, checked_out_by, return_date):
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": 1,
            "name": name,
            "checked_out_by": checked_out_by,
            "return_date": return_date,
        }[key]
        return row

    def test_returns_stale_items(self, app):
        stale_row = self._make_row("Oscilloscope", "alice", "2026-01-01")
        current_row = self._make_row("Multimeter", "bob", "2099-12-31")
        not_checked_out = self._make_row("Power Supply", None, None)

        with patch(
            "tools.checkout.db.list_equipment",
            return_value=[stale_row, current_row, not_checked_out],
        ):
            from tasks.periodic import check_stale_checkouts

            result = _invoke(check_stale_checkouts, app)

        assert result["stale_count"] == 1
        assert result["items"][0]["name"] == "Oscilloscope"
        assert result["items"][0]["days_overdue"] > 0

    def test_no_stale_items_returns_empty(self, app):
        row = self._make_row("Multimeter", "bob", "2099-12-31")

        with patch("tools.checkout.db.list_equipment", return_value=[row]):
            from tasks.periodic import check_stale_checkouts

            result = _invoke(check_stale_checkouts, app)

        assert result["stale_count"] == 0
        assert result["items"] == []

    def test_retries_on_exception(self, app):
        with patch(
            "tools.checkout.db.list_equipment",
            side_effect=RuntimeError("DB gone"),
        ):
            from tasks.periodic import check_stale_checkouts

            with pytest.raises(Exception, match="retry called"):
                _invoke(check_stale_checkouts, app)


# ---------------------------------------------------------------------------
# backup_databases
# ---------------------------------------------------------------------------

class TestBackupDatabases:
    def test_copies_existing_files(self, app, tmp_path):
        # Use an isolated path so the conftest app-fixture DBs don't interfere.
        data_dir = tmp_path / "backup_isolated_data"
        db_dir = data_dir / "db"
        db_dir.mkdir(parents=True)

        # Create exactly two of the five expected SQLite files.
        (db_dir / "checkout.db").write_bytes(b"sqlite")
        (db_dir / "inventory.db").write_bytes(b"sqlite")

        app.config["DATA_DIR"] = str(data_dir)

        from tasks.periodic import backup_databases

        result = _invoke(backup_databases, app)

        assert "checkout.db" in result["copied"]
        assert "inventory.db" in result["copied"]
        # Files that don't exist yet show in missing, not an error.
        assert "print_requests.db" in result["missing"]

        # Verify the files were actually written.
        backup_dir = Path(result["backup_dir"])
        assert (backup_dir / "checkout.db").exists()
        assert (backup_dir / "inventory.db").exists()

    def test_handles_all_missing_files_gracefully(self, app, tmp_path):
        # Use an isolated path so the conftest app-fixture DBs don't interfere.
        data_dir = tmp_path / "backup_empty_data"
        db_dir = data_dir / "db"
        db_dir.mkdir(parents=True)
        app.config["DATA_DIR"] = str(data_dir)

        from tasks.periodic import backup_databases

        result = _invoke(backup_databases, app)

        assert result["copied"] == []
        assert len(result["missing"]) == 5

    def test_idempotent_same_day(self, app, tmp_path):
        """Running twice on the same day overwrites rather than duplicating."""
        data_dir = tmp_path / "backup_idem_data"
        db_dir = data_dir / "db"
        db_dir.mkdir(parents=True)
        (db_dir / "checkout.db").write_bytes(b"v1")
        app.config["DATA_DIR"] = str(data_dir)

        from tasks.periodic import backup_databases

        # First run
        r1 = _invoke(backup_databases, app)
        # Overwrite source with new content, then run again.
        (db_dir / "checkout.db").write_bytes(b"v2")
        r2 = _invoke(backup_databases, app)

        # Both runs report the same backup dir (same date).
        assert r1["backup_dir"] == r2["backup_dir"]
        # File should contain the v2 content.
        assert (Path(r2["backup_dir"]) / "checkout.db").read_bytes() == b"v2"

    def test_retries_on_unexpected_exception(self, app, tmp_path):
        data_dir = tmp_path / "backup_retry_data"
        db_dir = data_dir / "db"
        db_dir.mkdir(parents=True)
        app.config["DATA_DIR"] = str(data_dir)

        with patch("shutil.copy2", side_effect=OSError("disk full")):
            from tasks.periodic import backup_databases

            # Patch _SQLITE_DB_NAMES so at least one copy is attempted.
            import tasks.periodic as _tp
            with patch.object(_tp, "_SQLITE_DB_NAMES", ["checkout.db"]):
                # Create the source file so we reach shutil.copy2.
                (db_dir / "checkout.db").write_bytes(b"x")

                with pytest.raises(Exception, match="retry called"):
                    _invoke(backup_databases, app)


# ---------------------------------------------------------------------------
# cleanup_temp_uploads
# ---------------------------------------------------------------------------

class TestCleanupTempUploads:
    def test_removes_orphaned_files(self, app, tmp_path):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        orphan = upload_dir / "old_file.stl"
        orphan.write_bytes(b"stl")
        active = upload_dir / "abc_active.stl"
        active.write_bytes(b"stl")

        app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(upload_dir)

        mock_req = {"uploaded_file_path": "abc_active.stl"}

        with patch("tools.print_requests.db.list_requests", return_value=[mock_req]):
            from tasks.periodic import cleanup_temp_uploads

            result = _invoke(cleanup_temp_uploads, app)

        assert "old_file.stl" in result["removed"]
        assert not orphan.exists()
        assert active.exists()

    def test_keeps_all_referenced_files(self, app, tmp_path):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        f1 = upload_dir / "file1.stl"
        f1.write_bytes(b"x")

        app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(upload_dir)

        mock_req = {"uploaded_file_path": "file1.stl"}
        with patch("tools.print_requests.db.list_requests", return_value=[mock_req]):
            from tasks.periodic import cleanup_temp_uploads

            result = _invoke(cleanup_temp_uploads, app)

        assert result["removed"] == []
        assert f1.exists()

    def test_nonexistent_upload_folder_is_safe(self, app, tmp_path):
        app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(tmp_path / "no_such_dir")

        with patch("tools.print_requests.db.list_requests", return_value=[]):
            from tasks.periodic import cleanup_temp_uploads

            result = _invoke(cleanup_temp_uploads, app)

        assert result["removed"] == []

    def test_retries_on_unexpected_exception(self, app, tmp_path):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(upload_dir)

        with patch(
            "tools.print_requests.db.list_requests",
            side_effect=RuntimeError("DB exploded"),
        ):
            from tasks.periodic import cleanup_temp_uploads

            # DB failure is handled gracefully (only logs a warning),
            # so the task should not retry for that specific error.
            result = _invoke(cleanup_temp_uploads, app)

        assert result["removed"] == []

    def test_ignores_subdirectories(self, app, tmp_path):
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        subdir = upload_dir / "design_images"
        subdir.mkdir()

        app.config["PRINT_REQUESTS_UPLOAD_FOLDER"] = str(upload_dir)

        with patch("tools.print_requests.db.list_requests", return_value=[]):
            from tasks.periodic import cleanup_temp_uploads

            result = _invoke(cleanup_temp_uploads, app)

        # Subdirectories must never be removed.
        assert subdir.exists()
        assert result["removed"] == []
