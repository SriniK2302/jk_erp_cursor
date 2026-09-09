"""JSON-backed storage for Gmail accounts used by the Gmail Processor.

Stores: email, credentials_path, token_path per account.
File lives outside git (media/gmail_accounts/accounts.json).
"""
import json
from pathlib import Path

from django.conf import settings

ACCOUNTS_FILE = Path(settings.MEDIA_ROOT) / "gmail_accounts" / "accounts.json"


def _ensure_file():
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ACCOUNTS_FILE.exists():
        ACCOUNTS_FILE.write_text("[]")


def load_accounts() -> list[dict]:
    _ensure_file()
    return json.loads(ACCOUNTS_FILE.read_text())


def save_accounts(accounts: list[dict]) -> None:
    _ensure_file()
    ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2))


def add_account(email: str) -> dict:
    accounts = load_accounts()
    account = {"email": email, "credentials_path": "", "token_path": ""}
    accounts.append(account)
    save_accounts(accounts)
    return account


def remove_account(email: str) -> None:
    accounts = load_accounts()
    accounts = [a for a in accounts if a["email"] != email]
    save_accounts(accounts)
