import json
import os
from pathlib import Path
from typing import Optional

from werkzeug.security import check_password_hash


def _accounts_path() -> Path:
    data_dir = os.environ.get("DATA_DIR", "./data")
    return Path(data_dir) / "accounts.json"


def load_accounts() -> dict:
    path = _accounts_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def verify_local_user(username: str, password: str) -> Optional[dict]:
    """Return the account dict if credentials are valid, else None."""
    accounts = load_accounts()
    account = accounts.get(username)
    if not account:
        return None
    if not check_password_hash(account["password_hash"], password):
        return None
    return account
