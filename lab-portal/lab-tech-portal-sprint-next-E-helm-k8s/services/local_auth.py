import json
import os
from pathlib import Path
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

# Valid local roles, ordered most → least privileged (mirrors rbac.TIERS).
# Each role string is also used as the Okta-group name so get_user_tier()
# resolves it correctly when RBAC_ADMIN_GROUPS etc. are set to match.
ROLES = ("admin", "lab-tech-lead", "lab-tech", "viewer")


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


def get_user_groups(account: dict) -> list[str]:
    """Return the groups list for a local account based on its role field.

    The role string doubles as the group name so that get_user_tier() in
    rbac.py resolves it correctly when RBAC_*_GROUPS config values are set
    to match (see app.py LOCAL_AUTH block).
    """
    role = account.get("role", "viewer")
    if role not in ROLES:
        role = "viewer"
    return [role]


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
    """Create a new account with viewer role. Returns an error string on failure, None on success."""
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
        "role": "viewer",
    }
    _save_accounts(accounts)
    return None
