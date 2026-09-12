"""Gmail management: bulk operations on a user's Gmail account.

This module is being rebuilt step by step, starting from lowest dependencies.
"""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from utilities.gmail_accounts_store import get_account, GMAIL_SCOPES
import threading
import time
import uuid

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
    """Apply label changes in chunks of 100 using batchModify (much faster than per-message calls).
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
        """Move every message (excluding Spam/Trash) into Inbox only, removing all other labels."""
        service = get_service(email)
        query = "-in:spam -in:trash"

        def list_progress(count):
            if progress_callback:
                progress_callback(0, max(count, 1))

        message_refs = []
        page_token = None
        while True:
            kwargs = {"userId": "me", "labelIds": [], "maxResults": 500, "q": query}
            if page_token:
                kwargs["pageToken"] = page_token
            result = service.users().messages().list(**kwargs).execute()
            message_refs.extend(result.get("messages", []))
            list_progress(len(message_refs))
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

