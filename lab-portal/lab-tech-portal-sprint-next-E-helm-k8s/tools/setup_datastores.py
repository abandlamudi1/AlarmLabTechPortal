"""Initialize local SQLite datastores with seed data."""
from __future__ import annotations

from tools.inventory.inventory_app import init_db
from tools.rf_chamber.rf_chamber_app import _ensure_db


def main() -> None:
    init_db()
    _ensure_db()
    print("Inventory and RF chamber databases are ready.")


if __name__ == "__main__":
    main()
