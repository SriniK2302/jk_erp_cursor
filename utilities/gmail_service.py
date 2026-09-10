"""Gmail API service helper: build an authenticated client and list labels."""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from utilities.gmail_accounts_store import get_account, GMAIL_SCOPES


def get_service(email: str):
    account = get_account(email)
    if account is None:
        raise ValueError(f"No account found for '{email}'.")
    if not account.get("token_path"):
        raise ValueError(f"'{email}' is not connected yet.")

    creds = Credentials.from_authorized_user_file(account["token_path"], GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds)


def list_labels(email: str) -> list[dict]:
    service = get_service(email)
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    return [{"id": l["id"], "name": l["name"]} for l in labels]
