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



def set_credentials_path(email: str, path: str) -> None:
    accounts = load_accounts()
    for a in accounts:
        if a["email"] == email:
            a["credentials_path"] = path
            break
    save_accounts(accounts)



def set_token_path(email: str, path: str) -> None:
    accounts = load_accounts()
    for a in accounts:
        if a["email"] == email:
            a["token_path"] = path
            break
    save_accounts(accounts)


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_account(email: str) -> dict | None:
    accounts = load_accounts()
    for a in accounts:
        if a["email"] == email:
            return a
    return None


def connect_account(email: str) -> None:
    """Run the OAuth2 consent flow for this account and save the token."""
    from pathlib import Path

    from google_auth_oauthlib.flow import InstalledAppFlow

    account = get_account(email)
    if account is None:
        raise ValueError(f"No account found for '{email}'.")
    if not account.get("credentials_path"):
        raise ValueError(f"No credentials.json set for '{email}'.")

    flow = InstalledAppFlow.from_client_secrets_file(account["credentials_path"], GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)

    token_dir = ACCOUNTS_FILE.parent / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    safe_name = email.replace("@", "_at_").replace(".", "_") + ".json"
    token_path = token_dir / safe_name
    token_path.write_text(creds.to_json())

    set_token_path(email, str(token_path))

