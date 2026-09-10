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



def _build_query(scope: str, keywords: str, has_attachment: bool) -> str:
    terms = [t.strip() for t in keywords.split("+") if t.strip()]
    if scope == "subject":
        parts = [f'subject:"{t}"' for t in terms]
    elif scope == "from":
        parts = [f'from:"{t}"' for t in terms]
    else:
        parts = [f'"{t}"' for t in terms]
    if has_attachment:
        parts.append("has:attachment")
    return " ".join(parts)


def search_messages(email: str, label_id: str, scope: str, keywords: str, has_attachment: bool) -> list[dict]:
    service = get_service(email)
    query = _build_query(scope, keywords, has_attachment)

    label_ids = [label_id] if label_id else []
    result = service.users().messages().list(userId="me", q=query, labelIds=label_ids, maxResults=50).execute()
    message_refs = result.get("messages", [])

    results = []
    for ref in message_refs:
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        has_att = any(
            part.get("filename") for part in msg.get("payload", {}).get("parts", []) or []
        )
        results.append({
            "id": ref["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "has_attachment": has_att,
        })
    return results
