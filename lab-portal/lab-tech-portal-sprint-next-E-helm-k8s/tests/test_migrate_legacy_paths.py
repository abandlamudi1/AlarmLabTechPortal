"""Tests for scripts/migrate_legacy_paths.py.

Issue #138: migrate legacy filesystem paths to opaque object-storage keys.

Covers:
  - is_legacy_path() detection
  - derive_opaque_key() key derivation
  - resolve_legacy_file() path resolution
  - migrate_column() per-column logic (migrate, skip-opaque, skip-missing)
  - main() integration (print_requests + inventory, idempotency, missing DBs)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Import the script as a module.
# Append the project root to sys.path so the relative import works.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.migrate_legacy_paths import (
    derive_opaque_key,
    is_legacy_path,
    main,
    migrate_column,
    resolve_legacy_file,
)
from services.object_storage import LocalFilesystemStorage


# ---------------------------------------------------------------------------
# Unit tests: is_legacy_path
# ---------------------------------------------------------------------------

class TestIsLegacyPath:
    def test_opaque_key_is_not_legacy(self):
        assert not is_legacy_path("abc123_model.stl")

    def test_empty_string_is_not_legacy(self):
        assert not is_legacy_path("")

    def test_relative_path_with_slash_is_legacy(self):
        assert is_legacy_path("data/uploads/abc123_model.stl")

    def test_absolute_path_is_legacy(self):
        assert is_legacy_path("/app/data/uploads/abc123_model.stl")

    def test_backslash_path_is_legacy(self):
        assert is_legacy_path("data\\uploads\\abc123.stl")

    def test_static_prefix_path_is_legacy(self):
        assert is_legacy_path("static/generated/inventory/qr_1.png")

    def test_design_images_key_is_not_legacy(self):
        assert not is_legacy_path("design_images/abc123_img.png")


# ---------------------------------------------------------------------------
# Unit tests: derive_opaque_key
# ---------------------------------------------------------------------------

class TestDeriveOpaqueKey:
    def test_absolute_path_extracts_basename(self):
        key = derive_opaque_key("/app/data/uploads/abc_model.stl", "print_requests/")
        assert key == "print_requests/abc_model.stl"

    def test_relative_path_with_prefix(self):
        key = derive_opaque_key("data/uploads/design_images/abc_img.png", "print_requests/images/")
        assert key == "print_requests/images/abc_img.png"

    def test_static_prefix_stripped(self):
        key = derive_opaque_key("static/generated/inventory/qr_1.png", "qr_codes/")
        assert key == "qr_codes/qr_1.png"

    def test_no_prefix(self):
        key = derive_opaque_key("data/uploads/qr_5.png")
        assert key == "qr_5.png"

    def test_backslash_normalised(self):
        key = derive_opaque_key("data\\uploads\\model.stl", "print_requests/")
        assert key == "print_requests/model.stl"


# ---------------------------------------------------------------------------
# Unit tests: resolve_legacy_file
# ---------------------------------------------------------------------------

class TestResolveLegacyFile:
    def test_absolute_path_found(self, tmp_path):
        f = tmp_path / "model.stl"
        f.write_bytes(b"solid")
        result = resolve_legacy_file(str(f), upload_root=tmp_path)
        assert result == f

    def test_absolute_path_missing(self, tmp_path):
        result = resolve_legacy_file("/nonexistent/path/model.stl", upload_root=tmp_path)
        assert result is None

    def test_relative_path_resolved_under_root(self, tmp_path):
        (tmp_path / "sub").mkdir()
        f = tmp_path / "sub" / "img.png"
        f.write_bytes(b"PNG")
        result = resolve_legacy_file("sub/img.png", upload_root=tmp_path)
        assert result == f

    def test_basename_fallback(self, tmp_path):
        """Falls back to basename-only search when full relative path not found."""
        f = tmp_path / "qr_1.png"
        f.write_bytes(b"PNG")
        # The stored value includes a static/ prefix, but the file is only at basename.
        result = resolve_legacy_file("static/generated/inventory/qr_1.png", upload_root=tmp_path)
        assert result == f

    def test_missing_file_returns_none(self, tmp_path):
        result = resolve_legacy_file("ghost.stl", upload_root=tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests: migrate_column
# ---------------------------------------------------------------------------

@pytest.fixture
def pr_db(tmp_path) -> Generator[tuple[sqlite3.Connection, Path], None, None]:
    """In-memory-style print_requests DB with one legacy-path row."""
    db_path = tmp_path / "print_requests.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE print_requests "
        "(id INTEGER PRIMARY KEY, uploaded_file_path TEXT, uploaded_image_path TEXT)"
    )
    conn.execute(
        "INSERT INTO print_requests (uploaded_file_path, uploaded_image_path) VALUES (?,?)",
        ("data/uploads/abc_model.stl", "data/uploads/design_images/abc_img.png"),
    )
    conn.commit()
    return conn, db_path


class TestMigrateColumn:
    def test_migrates_legacy_path_to_opaque_key(self, tmp_path, pr_db):
        conn, _ = pr_db

        # Create the legacy file so the migration can copy it.
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()
        (upload_root / "abc_model.stl").write_bytes(b"solid stl")
        # The relative path includes sub-dir; mirror that.
        (upload_root / "abc_model.stl").write_bytes(b"solid stl")

        storage = LocalFilesystemStorage(root_dir=str(tmp_path / "storage"))

        count = migrate_column(
            conn,
            table="print_requests",
            column="uploaded_file_path",
            storage=storage,
            upload_root=upload_root,
            key_prefix="print_requests/",
        )

        assert count == 1
        row = conn.execute("SELECT uploaded_file_path FROM print_requests WHERE id=1").fetchone()
        assert row[0] == "print_requests/abc_model.stl"
        # The file should now exist in storage.
        assert (tmp_path / "storage" / "print_requests" / "abc_model.stl").exists()

    def test_already_opaque_key_is_skipped(self, tmp_path, pr_db):
        conn, _ = pr_db

        # Overwrite with an already-opaque value.
        conn.execute(
            "UPDATE print_requests SET uploaded_file_path = ? WHERE id = 1",
            ("abc123_model.stl",),
        )
        conn.commit()

        storage = LocalFilesystemStorage(root_dir=str(tmp_path / "storage"))
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()

        count = migrate_column(
            conn,
            table="print_requests",
            column="uploaded_file_path",
            storage=storage,
            upload_root=upload_root,
        )

        assert count == 0  # Nothing to migrate.

    def test_missing_legacy_file_skipped_with_warning(self, tmp_path, pr_db, caplog):
        import logging
        conn, _ = pr_db

        # The legacy file does NOT exist on disk.
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()

        storage = LocalFilesystemStorage(root_dir=str(tmp_path / "storage"))

        with caplog.at_level(logging.WARNING):
            count = migrate_column(
                conn,
                table="print_requests",
                column="uploaded_file_path",
                storage=storage,
                upload_root=upload_root,
            )

        assert count == 0
        assert "not found on disk" in caplog.text
        # Row must remain unchanged.
        row = conn.execute("SELECT uploaded_file_path FROM print_requests WHERE id=1").fetchone()
        assert "data/uploads" in row[0]

    def test_idempotent_second_run_is_noop(self, tmp_path, pr_db):
        """After the first run the stored value is an opaque key; second run skips it."""
        conn, _ = pr_db
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()
        (upload_root / "abc_model.stl").write_bytes(b"stl bytes")

        storage = LocalFilesystemStorage(root_dir=str(tmp_path / "storage"))

        # No prefix — migrated key has no path separator, so it stays opaque.
        count1 = migrate_column(
            conn,
            table="print_requests",
            column="uploaded_file_path",
            storage=storage,
            upload_root=upload_root,
            key_prefix="",
        )
        count2 = migrate_column(
            conn,
            table="print_requests",
            column="uploaded_file_path",
            storage=storage,
            upload_root=upload_root,
            key_prefix="",
        )

        assert count1 == 1
        assert count2 == 0  # Second run is a no-op.


# ---------------------------------------------------------------------------
# Integration test: main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_migrates_both_dbs(self, tmp_path, monkeypatch):
        """main() migrates print_requests and inventory DBs end-to-end.

        Legacy paths are stored as absolute paths so resolution is unambiguous
        regardless of the test runner's CWD.
        """
        data_dir = tmp_path / "data"
        db_dir = data_dir / "db"
        upload_dir = data_dir / "uploads"
        images_dir = upload_dir / "design_images"
        qr_dir = data_dir / "generated" / "inventory"
        db_dir.mkdir(parents=True)
        upload_dir.mkdir(parents=True)
        images_dir.mkdir(parents=True)
        qr_dir.mkdir(parents=True)

        # Create the legacy files on disk.
        stl_file = upload_dir / "file_a.stl"
        img_file = images_dir / "img_a.png"
        qr_file = qr_dir / "qr_1.png"
        stl_file.write_bytes(b"stl")
        img_file.write_bytes(b"png")
        qr_file.write_bytes(b"qrpng")

        # Seed print_requests DB with absolute legacy paths.
        pr_db_path = db_dir / "print_requests.db"
        conn = sqlite3.connect(str(pr_db_path))
        conn.execute(
            "CREATE TABLE print_requests "
            "(id INTEGER PRIMARY KEY, uploaded_file_path TEXT, uploaded_image_path TEXT)"
        )
        conn.execute(
            "INSERT INTO print_requests (uploaded_file_path, uploaded_image_path) VALUES (?,?)",
            (str(stl_file), str(img_file)),  # absolute paths — pre-migration format
        )
        conn.commit()
        conn.close()

        # Seed inventory DB with static/-prefixed legacy path.
        inv_db_path = db_dir / "inventory.db"
        conn = sqlite3.connect(str(inv_db_path))
        conn.execute(
            "CREATE TABLE items "
            "(id INTEGER PRIMARY KEY, qr_code TEXT)"
        )
        conn.execute(
            "INSERT INTO items (qr_code) VALUES (?)",
            (str(qr_file),),  # absolute path — pre-migration format
        )
        conn.commit()
        conn.close()

        # Point env vars at tmp dirs.
        monkeypatch.setenv("DATA_DIR", str(data_dir))
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

        result = main()
        assert result == 0

        # Verify print_requests rows updated to opaque keys.
        # Model file keys have no path separators; image keys may have the
        # intentional "design_images/" namespace prefix (matches the pattern
        # used by _handle_design_image_upload for new rows).
        conn = sqlite3.connect(str(pr_db_path))
        row = conn.execute("SELECT uploaded_file_path, uploaded_image_path FROM print_requests WHERE id=1").fetchone()
        conn.close()
        assert "/" not in row[0] and "\\" not in row[0], f"uploaded_file_path still a path: {row[0]}"
        assert row[0] == "file_a.stl"
        # Image path is allowed to have the "design_images/" prefix — that is
        # the canonical form used by the app for new uploads.
        assert row[1] == "design_images/img_a.png", f"unexpected uploaded_image_path: {row[1]}"

        # Verify inventory row updated.
        conn = sqlite3.connect(str(inv_db_path))
        row = conn.execute("SELECT qr_code FROM items WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "qr_1.png"

    def test_main_is_idempotent(self, tmp_path, monkeypatch):
        """Running main() twice produces no additional changes on the second run."""
        data_dir = tmp_path / "data"
        db_dir = data_dir / "db"
        upload_dir = data_dir / "uploads"
        db_dir.mkdir(parents=True)
        upload_dir.mkdir(parents=True)

        stl_file = upload_dir / "model.stl"
        stl_file.write_bytes(b"stl")

        pr_db_path = db_dir / "print_requests.db"
        conn = sqlite3.connect(str(pr_db_path))
        conn.execute(
            "CREATE TABLE print_requests "
            "(id INTEGER PRIMARY KEY, uploaded_file_path TEXT, uploaded_image_path TEXT)"
        )
        conn.execute(
            "INSERT INTO print_requests (uploaded_file_path) VALUES (?)",
            (str(stl_file),),  # absolute path — pre-migration format
        )
        conn.commit()
        conn.close()

        monkeypatch.setenv("DATA_DIR", str(data_dir))
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

        assert main() == 0
        assert main() == 0  # Second run must not raise or produce errors.

        conn = sqlite3.connect(str(pr_db_path))
        row = conn.execute("SELECT uploaded_file_path FROM print_requests WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "model.stl"

    def test_main_handles_missing_dbs(self, tmp_path, monkeypatch):
        """main() exits 0 and logs warnings when DBs are absent."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        monkeypatch.setenv("DATA_DIR", str(data_dir))
        monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

        result = main()
        assert result == 0
