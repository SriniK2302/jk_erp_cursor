"""Gmail management: bulk operations on a user's Gmail account.

Built incrementally, lowest dependency first.
"""
import threading
import time
import uuid

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from utilities.gmail_accounts_store import get_account, GMAIL_SCOPES

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}

BATCH_SIZE = 100


def get_service(email: str):
    account = get_account(email)
    if account is None:
        raise ValueError(f"No account found for '{email}'.")
    if not account.get("token_path"):
        raise ValueError(f"'{email}' is not connected yet.")

    creds = Credentials.from_authorized_user_file(account["token_path"], GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds)


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


def _batch_modify(service, message_ids: list[str], add_label_ids: list[str] = None,
                  remove_label_ids: list[str] = None, progress_callback=None):
    """Apply label changes in chunks of BATCH_SIZE using batchModify (much faster than per-message calls).
    Automatically drops any label id Gmail rejects as invalid and retries."""
    import re

    total = len(message_ids)
    add_label_ids = list(add_label_ids) if add_label_ids else []
    remove_label_ids = list(remove_label_ids) if remove_label_ids else []

    done = 0
    for start in range(0, total, BATCH_SIZE):
        chunk = message_ids[start:start + BATCH_SIZE]
        attempts = 0
        while True:
            attempts += 1
            if attempts > 20:
                raise RuntimeError(f"Too many retries removing invalid labels at chunk starting {start}.")
            body = {"ids": chunk}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            try:
                service.users().messages().batchModify(userId="me", body=body).execute()
                break
            except Exception as exc:
                match = re.search(r"Invalid label:\s*([A-Za-z0-9_\-]+)", str(exc))
                if match:
                    bad_label = match.group(1)
                    before = len(add_label_ids) + len(remove_label_ids)
                    add_label_ids = [l for l in add_label_ids if l != bad_label]
                    remove_label_ids = [l for l in remove_label_ids if l != bad_label]
                    after = len(add_label_ids) + len(remove_label_ids)
                    if after == before:
                        raise RuntimeError(f"Label '{bad_label}' reported invalid but not found in current list: {exc}")
                    if progress_callback:
                        progress_callback(done, total)
                    continue
                raise
        done += len(chunk)
        if progress_callback:
            progress_callback(done, total)


def move_all_to_inbox(email: str, progress_callback=None) -> dict:
    """Move every message (excluding Inbox/Spam/Trash) into Inbox only, removing all other labels."""
    service = get_service(email)
    query = "-in:inbox -in:spam -in:trash"

    message_refs = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "labelIds": [], "maxResults": 500, "q": query}
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        message_refs.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    total = len(message_refs)
    message_ids = [ref["id"] for ref in message_refs]

    all_labels = service.users().labels().list(userId="me").execute().get("labels", [])
    remove_ids = [l["id"] for l in all_labels if l["id"] not in ("INBOX", "SPAM", "TRASH")]

    _batch_modify(service, message_ids, add_label_ids=["INBOX"], remove_label_ids=remove_ids,
                  progress_callback=progress_callback)

    return {"moved": total, "total": total}


def start_move_to_inbox_job(email: str) -> str:
    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "done": False,
            "current": 0,
            "total": 0,
            "message": "Starting…",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }

    def run():
        def progress(current, total):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["current"] = current
                    job["total"] = total
                    job["message"] = f"Moved {current} of {total} email(s)…"

        try:
            result = move_all_to_inbox(email, progress_callback=progress)
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["message"] = "Done."
                    job["result"] = result
        except Exception as exc:
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["error"] = str(exc) or f"{type(exc).__name__} (no message)"

    threading.Thread(target=run, daemon=True).start()
    return job_id


def get_job_status(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        return dict(_JOBS.get(job_id)) if job_id in _JOBS else None


SEARCH_PREF_KEYS = [
    "email",
    "label_id",
    "scope",
    "keywords",
    "target_label_name",
    "has_attachment",
]


def save_search_preferences(session, **kwargs) -> None:
    for key in SEARCH_PREF_KEYS:
        if key in kwargs:
            session[f"gmail_process_{key}"] = kwargs[key]


def load_search_preferences(session) -> dict:
    return {
        "initial_email": session.get("gmail_process_email", ""),
        "initial_label_id": session.get("gmail_process_label_id", ""),
        "initial_scope": session.get("gmail_process_scope", "subject"),
        "initial_keywords": session.get("gmail_process_keywords", ""),
        "initial_target_label_name": session.get("gmail_process_target_label_name", "Processed"),
        "initial_has_attachment": session.get("gmail_process_has_attachment", False),
    }


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


def search_messages(email: str, label_id: str, scope: str, keywords: str, has_attachment: bool, progress_callback=None) -> list[dict]:
    service = get_service(email)
    query = _build_query(scope, keywords, has_attachment)

    label_ids = [label_id] if label_id else []
    message_refs = _list_all_message_refs(service, label_ids, query)
    total = len(message_refs)

    results = []
    done = 0

    def _has_attachment_recursive(part):
        if part.get("filename"):
            return True
        for sub in part.get("parts", []) or []:
            if _has_attachment_recursive(sub):
                return True
        return False

    def handle_response(request_id, response, exception):
        if exception is not None:
            return
        headers = {h["name"]: h["value"] for h in response.get("payload", {}).get("headers", [])}
        has_att = _has_attachment_recursive(response.get("payload", {}))
        results.append({
            "id": response["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "has_attachment": has_att,
        })

    for start in range(0, total, BATCH_SIZE):
        chunk = message_refs[start:start + BATCH_SIZE]
        batch = service.new_batch_http_request(callback=handle_response)
        for ref in chunk:
            batch.add(
                service.users().messages().get(userId="me", id=ref["id"], format="full"),
                request_id=ref["id"],
            )
        batch.execute()
        done += len(chunk)
        if progress_callback:
            progress_callback(done, total)

    return results


def start_search_job(email: str, label_id: str, scope: str, keywords: str, has_attachment: bool) -> str:
    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "done": False,
            "current": 0,
            "total": 0,
            "message": "Starting search…",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }

    def run():
        def progress(current, total):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["current"] = current
                    job["total"] = total
                    job["message"] = f"Fetched {current} of {total} email(s)…"

        try:
            results = search_messages(email, label_id, scope, keywords, has_attachment, progress_callback=progress)
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["message"] = "Done."
                    job["result"] = results
        except Exception as exc:
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["error"] = str(exc) or f"{type(exc).__name__} (no message)"

    threading.Thread(target=run, daemon=True).start()
    return job_id


def get_or_create_label(service, name: str) -> str:
    import time as _time

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
            _time.sleep(1)
            label_id, found_name = find(name)
            if label_id:
                return label_id
        raise RuntimeError(
            f"Could not create or find label '{name}' after conflict. Original error: {exc}"
        )


def _save_attachment(service, message_id: str, filename: str, attachment_id: str, dest_dir) -> str:
    """Download one attachment's bytes and save it, sanitizing the filename and avoiding overwrites.
    Returns the saved path as a string."""
    import base64
    from pathlib import Path

    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    data = base64.urlsafe_b64decode(att["data"])

    dest_dir_path = Path(dest_dir)
    safe_filename = filename.replace("/", "-").replace("\\", "-")
    out_path = dest_dir_path / safe_filename
    if out_path.exists():
        out_path = dest_dir_path / f"{out_path.stem}_{message_id}{out_path.suffix}"
    out_path.write_bytes(data)
    return str(out_path)


def _fetch_messages_full(service, message_ids: list[str], progress_callback=None) -> dict:
    """Fetch full payloads for many messages using batching. Returns {message_id: payload_dict}.
    Messages that fail to fetch are simply omitted from the result."""
    total = len(message_ids)
    payloads = {}
    done = 0

    def handle_response(request_id, response, exception):
        if exception is not None:
            return
        payloads[request_id] = response

    for start in range(0, total, BATCH_SIZE):
        chunk = message_ids[start:start + BATCH_SIZE]
        batch = service.new_batch_http_request(callback=handle_response)
        for message_id in chunk:
            batch.add(
                service.users().messages().get(userId="me", id=message_id, format="full"),
                request_id=message_id,
            )
        batch.execute()
        done += len(chunk)
        if progress_callback:
            progress_callback(done, total)

    return payloads


def _expand_to_thread_ids(service, message_ids: list[str]) -> set:
    """Given a list of message ids, return the full set of message ids belonging to
    the same threads (so a whole conversation moves together, not just the matched message)."""
    thread_ids = set()
    for message_id in message_ids:
        msg = service.users().messages().get(userId="me", id=message_id, format="minimal").execute()
        thread_ids.add(msg["threadId"])

    all_message_ids = set(message_ids)
    for thread_id in thread_ids:
        thread = service.users().threads().get(userId="me", id=thread_id, format="minimal").execute()
        for m in thread.get("messages", []):
            all_message_ids.add(m["id"])

    return all_message_ids


def download_attachments_bulk(email: str, message_ids: list[str], dest_dir, source_label_id: str = "",
                               target_label_name: str = "Processed", progress_callback=None) -> dict:
    """Download attachments for each message id, then move the whole conversation (thread) to
    target_label_name, removing source_label_id and INBOX. One bad attachment or filename does
    not stop the run - it's recorded in 'failed_attachments' instead.
    Returns {"downloaded_files": int, "messages_processed": int, "messages_with_no_attachment": int,
             "moved": int, "failed_attachments": list}."""
    from pathlib import Path

    service = get_service(email)
    dest_dir_path = Path(dest_dir)
    dest_dir_path.mkdir(parents=True, exist_ok=True)

    total = len(message_ids)
    downloaded_files = 0
    messages_with_no_attachment = 0
    failed_attachments = []

    payloads = _fetch_messages_full(service, message_ids, progress_callback=progress_callback)

    for message_id in message_ids:
        payload_msg = payloads.get(message_id)
        if payload_msg is None:
            failed_attachments.append({"message_id": message_id, "error": "Could not fetch message."})
            continue

        parts = payload_msg.get("payload", {}).get("parts", []) or []
        saved_any = False
        for part in parts:
            filename = part.get("filename")
            att_id = part.get("body", {}).get("attachmentId")
            if not filename or not att_id:
                continue
            try:
                _save_attachment(service, message_id, filename, att_id, dest_dir_path)
                downloaded_files += 1
                saved_any = True
            except Exception as exc:
                failed_attachments.append({"message_id": message_id, "filename": filename, "error": str(exc)})
        if not saved_any:
            messages_with_no_attachment += 1

    all_message_ids = _expand_to_thread_ids(service, message_ids)

    target_label_id = get_or_create_label(service, target_label_name)
    remove_ids = ["INBOX"]
    if source_label_id and source_label_id != "INBOX":
        remove_ids.append(source_label_id)
    _batch_modify(service, list(all_message_ids), add_label_ids=[target_label_id], remove_label_ids=remove_ids)

    return {
        "downloaded_files": downloaded_files,
        "messages_processed": total,
        "messages_with_no_attachment": messages_with_no_attachment,
        "moved": len(all_message_ids),
        "failed_attachments": failed_attachments,
    }


def start_download_job(email: str, message_ids: list[str], dest_dir, source_label_id: str = "",
                        target_label_name: str = "Processed") -> str:
    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "done": False,
            "current": 0,
            "total": 0,
            "message": "Starting download…",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }

    def run():
        def progress(current, total):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["current"] = current
                    job["total"] = total
                    job["message"] = f"Downloaded {current} of {total} email(s)…"

        try:
            result = download_attachments_bulk(
                email, message_ids, dest_dir,
                source_label_id=source_label_id,
                target_label_name=target_label_name,
                progress_callback=progress,
            )
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["message"] = "Done."
                    job["result"] = result
        except Exception as exc:
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["error"] = str(exc) or f"{type(exc).__name__} (no message)"

    threading.Thread(target=run, daemon=True).start()
    return job_id
