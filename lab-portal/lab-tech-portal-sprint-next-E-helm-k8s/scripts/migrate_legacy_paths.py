"""scripts/migrate_legacy_paths.py

Idempotent migration: legacy filesystem paths -> object-storage keys.

Background
----------
Sprint 8, Issue #29 introduced the ``ObjectStorage`` abstraction.  New DB rows
store opaque keys (e.g. ``abc123_model.stl`` or ``qr_1.png``).  Pre-existing
rows store legacy filesystem paths in one of three forms:

  - Absolute path:  ``/app/data/uploads/abc123_model.stl``
  - Relative path:  ``data/uploads/abc123_model.stl``
  - ``static/`` prefix: ``static/generated/inventory/qr_1.png``  (inventory
    legacy, normalised to basename only)

This script migrates all three cases so that only opaque keys remain in the DB.
The ``url_for()`` path-detection shim in ``LocalFilesystemStorage`` can then be
removed (see issue #138).

Idempotency
-----------
A value is considered *already migrated* if it contains no path separators (no
``/`` or ``\\``) and is not an absolute path.  Such values are skipped silently,
so the script is safe to re-run at any time.

Non-destructive
---------------
Legacy files on disk are **not** deleted.  The migration only:
  1. Copies the file bytes into object storage under the derived opaque key.
  2. Updates the DB row to the new opaque key.

If a legacy file is missing from disk the row is skipped with a WARNING so the
run can complete for all other rows.

Usage
-----
Run from the project root with the virtualenv active::

    python scripts/migrate_legacy_paths.py

Environment variables:

  DATA_DIR
      Root data directory (default: ``./data``).  Used to locate the SQLite
      databases and as the uploads root for ``LocalFilesystemStorage``.

  PRINT_REQUESTS_DB_PATH
      Override the print_requests SQLite path (default: DATA_DIR/db/print_requests.db).

  INVENTORY_DB_PATH
      Override the inventory SQLite path (default: DATA_DIR/db/inventory.db).

  OBJECT_STORAGE_BACKEND
      ``local`` (default) or ``s3``.  Passed through to ``get_storage()``.

  S3_BUCKET, S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION
      Required when ``OBJECT_STORAGE_BACKEND=s3``.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_LEGACY_PATH_PREFIXES = ("data/", "static/", "uploads/", "generated/")


def is_legacy_path(value: str) -> bool:
    """Return True if *value* looks like a filesystem path, not an opaque key.

    Legacy paths are:
    - Absolute filesystem paths (starts with an OS path separator)
    - Relative paths rooted at known legacy directories (``data/``, ``static/``)
    - Windows backslash-separated paths

    Opaque keys with a namespace prefix (e.g. ``design_images/<file>``) are
    NOT legacy paths and return False so that already-migrated rows are skipped.
    """
    if not value:
        return False
    if os.path.isabs(value):
        return True
    if "\\" in value:
        return True
    return any(value.startswith(p) for p in _LEGACY_PATH_PREFIXES)


def derive_opaque_key(value: str, key_prefix: str = "") -> str:
    """Return the opaque key to use when storing *value* in object storage.

    The key is ``<key_prefix><basename>`` where *basename* is the final
    component of the legacy path with any leading ``static/`` segment stripped.

    Examples:
        derive_opaque_key("/app/data/uploads/abc_model.stl", "print_requests/")
            -> "print_requests/abc_model.stl"

        derive_opaque_key("data/uploads/design_images/abc_img.png", "print_requests/images/")
            -> "print_requests/images/abc_img.png"

        derive_opaque_key("static/generated/inventory/qr_1.png", "qr_codes/")
            -> "qr_codes/qr_1.png"
    """
    # Strip legacy "static/" prefix used by the inventory tool.
    normalised = value.replace("\\", "/")
    if normalised.startswith("static/"):
        normalised = normalised.split("/", 1)[1]
    basename = Path(normalised).name
    return f"{key_prefix}{basename}"


def resolve_legacy_file(value: str, upload_root: Path) -> Path | None:
    """Return the absolute Path of the legacy file, or None if not found.

    Tries, in order:
      1. The value as an absolute path (if it is one).
      2. The full relative value joined onto the project root (CWD) — covers
         cases like ``data/uploads/design_images/img.png`` where the path is
         relative to the project root, not to upload_root itself.
      3. The full relative value joined onto upload_root — covers cases where
         the path was stored relative to the upload root.
      4. basename only under upload_root — last-resort for inventory QR paths.
    """
    # Absolute path: use directly.
    if os.path.isabs(value):
        p = Path(value)
        if p.exists():
            return p
        return None

    normalised = value.replace("\\", "/")
    # Strip static/ prefix for inventory QR paths.
    if normalised.startswith("static/"):
        normalised = normalised.split("/", 1)[1]

    # Try: relative to process CWD (project root) — handles paths like
    # "data/uploads/design_images/img.png" stored as project-relative values.
    cwd_candidate = Path(normalised)
    if cwd_candidate.exists():
        return cwd_candidate.resolve()

    # Try: full relative path under upload_root.
    candidate = upload_root / normalised
    if candidate.exists():
        return candidate

    # Try: basename only under upload_root (last resort, e.g. inventory QR).
    basename_candidate = upload_root / Path(normalised).name
    if basename_candidate.exists():
        return basename_candidate

    return None


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------

def migrate_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    storage,
    upload_root: Path,
    key_prefix: str = "",
) -> int:
    """Migrate all legacy-path values in *table.column* to opaque object-storage keys.

    Returns the number of rows actually migrated (already-opaque rows are skipped).
    """
    cursor = conn.execute(
        f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL"  # noqa: S608
    )
    rows = cursor.fetchall()

    migrated = 0
    skipped_already_opaque = 0
    skipped_missing_file = 0

    for row_id, value in rows:
        value = str(value)

        if not is_legacy_path(value):
            skipped_already_opaque += 1
            continue  # Already an opaque key — idempotent skip.

        opaque_key = derive_opaque_key(value, key_prefix)
        legacy_file = resolve_legacy_file(value, upload_root)

        if legacy_file is None:
            logger.warning(
                "Legacy file not found on disk — skipping: table=%s column=%s id=%d value=%r",
                table,
                column,
                row_id,
                value,
            )
            skipped_missing_file += 1
            continue

        # Copy bytes into object storage.
        with open(legacy_file, "rb") as fh:
            storage.put_stream(opaque_key, fh)

        # Update DB row to the new opaque key.
        conn.execute(
            f"UPDATE {table} SET {column} = ? WHERE id = ?",  # noqa: S608
            (opaque_key, row_id),
        )

        logger.info(
            "Migrated: table=%s column=%s id=%d  %r -> %r",
            table,
            column,
            row_id,
            value,
            opaque_key,
        )
        migrated += 1

    conn.commit()
    logger.info(
        "Column %s.%s: migrated=%d  already_opaque=%d  missing_file=%d",
        table,
        column,
        migrated,
        skipped_already_opaque,
        skipped_missing_file,
    )
    return migrated


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the migration.  Returns 0 on success, 1 on configuration error."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    upload_root = data_dir / "uploads"

    # DB paths.
    default_pr_db = data_dir / "db" / "print_requests.db"
    default_inv_db = data_dir / "db" / "inventory.db"
    pr_db_path = Path(os.environ.get("PRINT_REQUESTS_DB_PATH", str(default_pr_db)))
    inv_db_path = Path(os.environ.get("INVENTORY_DB_PATH", str(default_inv_db)))

    # Build object storage backend.
    # Inline config dict so we don't need a Flask app context.
    storage_config: dict = {
        "OBJECT_STORAGE_BACKEND": os.environ.get("OBJECT_STORAGE_BACKEND", "local"),
        "DATA_DIR": str(data_dir),
        "S3_BUCKET": os.environ.get("S3_BUCKET", ""),
        "S3_ENDPOINT_URL": os.environ.get("S3_ENDPOINT_URL", ""),
        "S3_ACCESS_KEY": os.environ.get("S3_ACCESS_KEY", ""),
        "S3_SECRET_KEY": os.environ.get("S3_SECRET_KEY", ""),
        "S3_REGION": os.environ.get("S3_REGION", "us-east-1"),
    }

    # Import here so the script can be run without a full app import.
    try:
        from services.object_storage import get_storage
    except ImportError:
        logger.error(
            "Could not import services.object_storage.  Run this script from "
            "the project root with the virtualenv active."
        )
        return 1

    try:
        storage = get_storage(storage_config)
    except (ValueError, RuntimeError) as exc:
        logger.error("Failed to initialise object storage: %s", exc)
        return 1

    logger.info(
        "Starting legacy-path migration  data_dir=%s  backend=%s",
        data_dir,
        storage_config["OBJECT_STORAGE_BACKEND"],
    )

    total_migrated = 0

    # ------------------------------------------------------------------
    # Migrate print_requests
    # ------------------------------------------------------------------
    if pr_db_path.exists():
        pr_conn = sqlite3.connect(str(pr_db_path))
        try:
            pr_conn.execute("PRAGMA journal_mode=WAL")
            pr_conn.execute("PRAGMA busy_timeout=5000")

            total_migrated += migrate_column(
                pr_conn,
                table="print_requests",
                column="uploaded_file_path",
                storage=storage,
                upload_root=upload_root,
                key_prefix="",
            )
            total_migrated += migrate_column(
                pr_conn,
                table="print_requests",
                column="uploaded_image_path",
                storage=storage,
                upload_root=upload_root,
                key_prefix="design_images/",
            )
        finally:
            pr_conn.close()
    else:
        logger.warning(
            "print_requests DB not found at %s — skipping (not deployed yet?)",
            pr_db_path,
        )

    # ------------------------------------------------------------------
    # Migrate inventory items
    # ------------------------------------------------------------------
    # QR PNGs were historically written to DATA_DIR/generated/inventory/
    # (see _qr_dir() in inventory_app.py).  Use that as the upload root
    # when resolving legacy QR paths.
    qr_root = data_dir / "generated" / "inventory"

    if inv_db_path.exists():
        inv_conn = sqlite3.connect(str(inv_db_path))
        try:
            inv_conn.execute("PRAGMA journal_mode=WAL")
            inv_conn.execute("PRAGMA busy_timeout=5000")

            total_migrated += migrate_column(
                inv_conn,
                table="items",
                column="qr_code",
                storage=storage,
                upload_root=qr_root,
                key_prefix="",
            )
        finally:
            inv_conn.close()
    else:
        logger.warning(
            "inventory DB not found at %s — skipping (not deployed yet?)",
            inv_db_path,
        )

    logger.info("Migration complete.  Total rows migrated: %d", total_migrated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
