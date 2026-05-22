import json
import os
from pathlib import Path
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash


def _accounts_path() -> Path:
    data_dir = os.environ.get("DATA_DIR", "./data")
    return Path(data_dir) / "accounts.json"


def load_accounts() -> dict:
    path = _accounts_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_accounts(accounts: dict) -> None:
    path = _accounts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(accounts, f, indent=2)


def verify_local_user(username: str, password: str) -> Optional[dict]:
    """Return the account dict if credentials are valid, else None."""
    accounts = load_accounts()
    account = accounts.get(username)
    if not account:
        return None
    if not check_password_hash(account["password_hash"], password):
        return None
    return account


def create_local_user(username: str, display_name: str, email: str, password: str) -> Optional[str]:
    """Create a new account. Returns an error string on failure, None on success."""
    if not username or not display_name or not email or not password:
        return "All fields are required."
    accounts = load_accounts()
    if username in accounts:
        return "That username is already taken."
    if any(a["email"].lower() == email.lower() for a in accounts.values()):
        return "An account with that email already exists."
    accounts[username] = {
        "username": username,
        "display_name": display_name,
        "email": email,
        "password_hash": generate_password_hash(password),
    }
    _save_accounts(accounts)
    return None
