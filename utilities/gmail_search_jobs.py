"""Background job runner for Gmail search with progress tracking."""
import threading
import time
import uuid

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


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
        from utilities.gmail_service import search_messages

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


def start_unique_subjects_job(email: str, label_id: str, scope: str = "subject", keywords: str = "", has_attachment: bool = False) -> str:

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
        from utilities.gmail_service import list_unique_subjects

        def progress(current, total):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["current"] = current
                    job["total"] = total
                    job["message"] = f"Scanned {current} of {total} email(s)…"

        try:
            subjects = list_unique_subjects(email, label_id, scope=scope, keywords=keywords, has_attachment=has_attachment, progress_callback=progress)

            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["message"] = "Done."
                    job["result"] = subjects
        except Exception as exc:
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["error"] = str(exc) or f"{type(exc).__name__} (no message)"

    threading.Thread(target=run, daemon=True).start()
    return job_id



def start_download_job(email: str, message_ids: list[str], dest_dir, source_label_id: str = "", target_label_name: str = "Processed") -> str:
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
        from utilities.gmail_service import download_attachments_bulk

        def progress(current, total):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if job:
                    job["current"] = current
                    job["total"] = total
                    job["message"] = f"Downloaded {current} of {total} email(s)…"

        try:
            result = download_attachments_bulk(email, message_ids, dest_dir, source_label_id=source_label_id, target_label_name=target_label_name, progress_callback=progress)
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
        from utilities.gmail_service import move_all_to_inbox

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



