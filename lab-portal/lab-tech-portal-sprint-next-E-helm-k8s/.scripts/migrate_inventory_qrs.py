#!/usr/bin/env python3
"""Move legacy QR PNG files from tools/inventory/static/ to DATA_DIR/generated/inventory/.

Slice D-part1, Issue #47. Run this script ONCE after deploying the Slice D-part1
changes to migrate any QR PNGs that were written by the old code path.

Usage
-----
    DATA_DIR=/data python .scripts/migrate_inventory_qrs.py

Environment variables
---------------------
DATA_DIR    Target root directory (default: ./data). The script creates
            DATA_DIR/generated/inventory/ if it does not exist.

SQL involved
------------
    SELECT id, qr_code FROM items WHERE qr_code IS NOT NULL;
    UPDATE items SET qr_code = '<filename>' WHERE id = <id>;

The qr_code column stores the bare filename (e.g. "qr_42.png"). No path
prefix is stored — the application resolves the full path at runtime via
DATA_DIR/generated/inventory/<filename>.

Idempotency
-----------
- If the destination file already exists, the source is NOT overwritten.
- If the source file does not exist (already moved or never generated), the
  row is skipped without error.
- Running the script twice produces the same result as running it once.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY_STATIC_DIR = os.path.join(_REPO_ROOT, "tools", "inventory", "static")

_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(_REPO_ROOT, "data"))
_DB_DIR = os.path.join(_DATA_DIR, "db")
_QR_DIR = os.path.join(_DATA_DIR, "generated", "inventory")
_DB_PATH = os.path.join(_DB_DIR, "inventory.db")


def main() -> None:
    if not os.path.exists(_DB_PATH):
        print(f"No inventory DB found at {_DB_PATH}. Nothing to migrate.", file=sys.stderr)
        sys.exit(0)

    os.makedirs(_QR_DIR, exist_ok=True)

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, qr_code FROM items WHERE qr_code IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    moved = 0
    skipped_missing = 0
    skipped_existing = 0
    errors = 0

    for row in rows:
        item_id = row["id"]
        qr_value = (row["qr_code"] or "").strip()
        if not qr_value:
            continue

        # Strip any leading "static/" prefix written by very old code.
        bare_name = qr_value.lstrip("/").split("/")[-1]

        dest_path = os.path.join(_QR_DIR, bare_name)

        if os.path.exists(dest_path):
            # Already at the new location — idempotent, skip.
            skipped_existing += 1
            continue

        src_path = os.path.join(_LEGACY_STATIC_DIR, bare_name)
        if not os.path.exists(src_path):
            print(f"  [SKIP] item {item_id}: source {src_path!r} not found", file=sys.stderr)
            skipped_missing += 1
            continue

        try:
            shutil.move(src_path, dest_path)
            print(f"  [MOVE] item {item_id}: {src_path!r} -> {dest_path!r}")
            moved += 1
        except OSError as exc:
            print(f"  [ERROR] item {item_id}: {exc}", file=sys.stderr)
            errors += 1

    print(
        f"\nDone. moved={moved} skipped_already_at_dest={skipped_existing}"
        f" skipped_no_source={skipped_missing} errors={errors}"
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
