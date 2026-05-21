#!/usr/bin/env python3
"""Rewrite absolute upload paths in print_requests DB to relative paths.

Slice D-part1, Issue #3. Run this script ONCE after deploying the Slice D-part1
changes on any environment that has rows with absolute paths written by the
old code (paths starting with / or a Windows drive letter).

Usage
-----
    DATA_DIR=/data python .scripts/migrate_print_request_paths.py

Environment variables
---------------------
DATA_DIR    Root directory used by the app (default: ./data). The script uses
            DATA_DIR/uploads/ as the anchor to strip from absolute paths.

SQL involved
------------
    SELECT id, uploaded_file_path, uploaded_image_path
      FROM print_requests
     WHERE uploaded_file_path IS NOT NULL
        OR uploaded_image_path IS NOT NULL;

    UPDATE print_requests
       SET uploaded_file_path  = '<relative>',
           uploaded_image_path = '<relative>'
     WHERE id = <id>;

Relative path convention (#3)
------------------------------
Values stored in the DB are relative to DATA_DIR/uploads/.
  "abc123_model.stl"            -> model file at uploads/abc123_model.stl
  "design_images/abc123_img.png" -> image file at uploads/design_images/abc123_img.png

Idempotency
-----------
- Rows whose paths are already relative (do NOT start with /) are skipped.
- Rows that cannot be made relative (path does not live under the uploads root)
  are logged as warnings and left unchanged.
- Running the script twice produces the same result as running it once.
"""
from __future__ import annotations

import os
import sqlite3
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_REPO_ROOT, "data"))
_DB_DIR = os.path.join(_DATA_DIR, "db")
_UPLOAD_ROOT = os.path.join(_DATA_DIR, "uploads") + os.sep
_DB_PATH = os.path.join(_DB_DIR, "print_requests.db")


def _to_relative(abs_path: str) -> str | None:
    """Return a path relative to _UPLOAD_ROOT, or None if not under it."""
    # Normalise OS separators.
    norm = os.path.normpath(abs_path)
    upload_root_norm = os.path.normpath(_UPLOAD_ROOT)
    # Try standard prefix strip.
    try:
        return os.path.relpath(norm, upload_root_norm)
    except ValueError:
        # Different drives on Windows — cannot relativise.
        return None


def _is_already_relative(path: str) -> bool:
    """Return True when the stored value looks like a relative path."""
    if not path:
        return True
    return not os.path.isabs(path)


def main() -> None:
    if not os.path.exists(_DB_PATH):
        print(f"No print_requests DB found at {_DB_PATH}. Nothing to migrate.", file=sys.stderr)
        sys.exit(0)

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, uploaded_file_path, uploaded_image_path"
            " FROM print_requests"
            " WHERE uploaded_file_path IS NOT NULL OR uploaded_image_path IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    updated = 0
    skipped_relative = 0
    skipped_not_under_root = 0
    errors = 0

    conn = sqlite3.connect(_DB_PATH)
    try:
        for row in rows:
            request_id = row["id"]
            file_path = row["uploaded_file_path"]
            image_path = row["uploaded_image_path"]

            new_file: str | None = file_path
            new_image: str | None = image_path
            changed = False

            for attr_name, stored_path in (
                ("uploaded_file_path", file_path),
                ("uploaded_image_path", image_path),
            ):
                if not stored_path:
                    continue
                if _is_already_relative(stored_path):
                    skipped_relative += 1
                    continue
                relative = _to_relative(stored_path)
                if relative is None or relative.startswith(".."):
                    print(
                        f"  [WARN] request {request_id} {attr_name}={stored_path!r}"
                        " is not under the upload root — leaving unchanged",
                        file=sys.stderr,
                    )
                    skipped_not_under_root += 1
                    continue
                # Normalise to forward slashes for cross-platform consistency.
                relative = relative.replace("\\", "/")
                print(
                    f"  [UPDATE] request {request_id} {attr_name}: {stored_path!r} -> {relative!r}"
                )
                if attr_name == "uploaded_file_path":
                    new_file = relative
                else:
                    new_image = relative
                changed = True

            if changed:
                try:
                    conn.execute(
                        "UPDATE print_requests"
                        " SET uploaded_file_path = ?, uploaded_image_path = ?"
                        " WHERE id = ?",
                        (new_file, new_image, request_id),
                    )
                    updated += 1
                except sqlite3.Error as exc:
                    print(f"  [ERROR] request {request_id}: {exc}", file=sys.stderr)
                    errors += 1

        conn.commit()
    finally:
        conn.close()

    print(
        f"\nDone. updated={updated} skipped_already_relative={skipped_relative}"
        f" skipped_not_under_root={skipped_not_under_root} errors={errors}"
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
