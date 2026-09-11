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

def get_or_create_label(service, name: str) -> str:
    import time

    def find(target_name):
        result = service.users().labels().list(userId="me").execute()
        for label in result.get("labels", []):
            if label["name"].strip().lower() == target_name.strip().lower():
                return label["id"], label["name"]
        return None, None

    label_id, _ = find(name)
    if label_id:
        return label_id

    try:
        created = service.users().labels().create(
            userId="me", body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        ).execute()
        return created["id"]
    except Exception as exc:
        for attempt in range(5):
            time.sleep(1)
            label_id, found_name = find(name)
            if label_id:
                return label_id
        raise RuntimeError(
            f"Could not create or find label '{name}' after conflict. Original error: {exc}"
        )


def _batch_modify(service, message_ids: list[str], add_label_ids: list[str] = None,
                  remove_label_ids: list[str] = None, progress_callback=None):
    """Apply label changes in chunks of 1000 using batchModify (much faster than per-message calls)."""
    total = len(message_ids)
    body_base = {}
    if add_label_ids:
        body_base["addLabelIds"] = add_label_ids
    if remove_label_ids:
        body_base["removeLabelIds"] = remove_label_ids

    done = 0
    for start in range(0, total, 1000):
        chunk = message_ids[start:start + 1000]
        body = dict(body_base)
        body["ids"] = chunk
        service.users().messages().batchModify(userId="me", body=body).execute()
        done += len(chunk)
        if progress_callback:
            progress_callback(done, total)


def move_all_to_inbox(email: str, progress_callback=None) -> dict:
    """Add INBOX label to every message not already in Inbox, excluding Spam and Trash."""
    service = get_service(email)
    query = "-in:inbox -in:spam -in:trash"
    message_refs = _list_all_message_refs(service, [], query)
    total = len(message_refs)
    message_ids = [ref["id"] for ref in message_refs]

    _batch_modify(service, message_ids, add_label_ids=["INBOX"], progress_callback=progress_callback)

    return {"moved": total, "total": total}
            service.users().messages().batchModify(userId="me", body=body).execute()
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)

    def move_all_to_inbox(email: str, progress_callback=None) -> dict:
        """Add INBOX label to every message not already in Inbox, excluding Spam and Trash."""
        service = get_service(email)
        query = "-in:inbox -in:spam -in:trash"
        message_refs = _list_all_message_refs(service, [], query)
        total = len(message_refs)
        message_ids = [ref["id"] for ref in message_refs]

        _batch_modify(service, message_ids, add_label_ids=["INBOX"], progress_callback=progress_callback)

        return {"moved": total, "total": total}



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

def download_attachments_for_message(service, message_id: str, dest_dir) -> list[str]:
    """Download all attachments of one message into dest_dir. Returns list of saved filenames."""
    from pathlib import Path
    import base64

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    parts = msg.get("payload", {}).get("parts", []) or []

    saved = []
    for part in parts:
        filename = part.get("filename")
        body = part.get("body", {})
        att_id = body.get("attachmentId")
        if not filename or not att_id:
            continue
        att = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=att_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])
        out_path = dest_dir / filename
        out_path.write_bytes(data)
        saved.append(str(out_path))
    return saved

def download_attachments_bulk(email: str, message_ids: list[str], dest_dir, source_label_id: str = "", target_label_name: str = "Processed", progress_callback=None) -> dict:
    """Download attachments for each message id, then move all of them to target_label_name
    (removing source_label_id and INBOX). Download progress calls progress_callback(current, total)
    during the download phase; the label move is done in one batch call at the end.
    Returns {"downloaded_files": int, "messages_processed": int, "messages_with_no_attachment": int, "moved": int}."""
    service = get_service(email)
    total = len(message_ids)
    downloaded_files = 0
    messages_with_no_attachment = 0

    for i, message_id in enumerate(message_ids, start=1):
        saved = download_attachments_for_message(service, message_id, dest_dir)
        if saved:
            downloaded_files += len(saved)
        else:
            messages_with_no_attachment += 1
        if progress_callback:
            progress_callback(i, total)

    target_label_id = get_or_create_label(service, target_label_name)
    remove_ids = ["INBOX"]
    if source_label_id and source_label_id != "INBOX":
        remove_ids.append(source_label_id)
    _batch_modify(service, message_ids, add_label_ids=[target_label_id], remove_label_ids=remove_ids)

    return {
        "downloaded_files": downloaded_files,
        "messages_processed": total,
        "messages_with_no_attachment": messages_with_no_attachment,
        "moved": total,
    }


def list_unique_subjects(email: str, label_id: str, scope: str = "subject", keywords: str = "", has_attachment: bool = False, progress_callback=None) -> list[str]:
    service = get_service(email)
    label_ids = [label_id] if label_id else []
    query = _build_query(scope, keywords, has_attachment)
    message_refs = _list_all_message_refs(service, label_ids, query)
    total = len(message_refs)

    subjects = []
    seen = set()
    for i, ref in enumerate(message_refs, start=1):
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata", metadataHeaders=["Subject"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        if subject not in seen:
            seen.add(subject)
            subjects.append(subject)
        if progress_callback:
            progress_callback(i, total)
    return subjects

def _list_all_message_refs(service, label_ids: list[str], query: str = "") -> list[dict]:
    refs = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "labelIds": label_ids, "maxResults": 500}
        if query:
            kwargs["q"] = query
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        refs.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return refs


def search_messages(email: str, label_id: str, scope: str, keywords: str, has_attachment: bool, progress_callback=None) -> list[dict]:
    service = get_service(email)
    query = _build_query(scope, keywords, has_attachment)

    label_ids = [label_id] if label_id else []
    message_refs = _list_all_message_refs(service, label_ids, query)
    total = len(message_refs)


    results = []
    for i, ref in enumerate(message_refs, start=1):
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
        if progress_callback:
            progress_callback(i, total)
    return results

