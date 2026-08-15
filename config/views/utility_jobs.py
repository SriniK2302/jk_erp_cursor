from config.views._std_imports import *  # noqa: F403

_DUPLICATE_JOBS_LOCK = threading.Lock()
_DUPLICATE_JOBS: dict[str, dict] = {}
_SIMILAR_JOBS_LOCK = threading.Lock()
_SIMILAR_JOBS: dict[str, dict] = {}
_SIMILAR_REF_JOBS_LOCK = threading.Lock()
_SIMILAR_REF_JOBS: dict[str, dict] = {}
_EXCEL_IMPORT_JOBS_LOCK = threading.Lock()
_EXCEL_IMPORT_JOBS: dict[str, dict] = {}
def _save_excel_import_preferences(
    request,
    *,
    postgres_db: str | None = None,
    sheet_name: str | None = None,
    table_name: str | None = None,
    selected_headers: list[str] | None = None,
) -> None:
    if postgres_db is not None:
        request.session["data_excel_import_postgres_db"] = postgres_db
    if sheet_name is not None:
        request.session["data_excel_import_sheet_name"] = sheet_name
    if table_name is not None:
        request.session["data_excel_import_table_name"] = table_name
    if selected_headers is not None:
        cleaned = [x.strip() for x in selected_headers if x and x.strip()]
        request.session["data_excel_import_selected_headers"] = cleaned


def _duplicate_progress_percent(phase: str, current: int, total: int | None) -> int:
    if phase == "collecting":
        if total:
            return 35
        return min(30, 5 + (current // 250))
    if phase == "hashing":
        if total and total > 0:
            return 35 + int((current / total) * 40)
        return 45
    if phase == "moving":
        if total and total > 0:
            return 75 + int((current / total) * 24)
        return 95
    if phase == "done":
        return 100
    if phase == "error":
        return 100
    return 10


def _start_duplicate_job(job_id: str, source_root: Path, target_root: Path) -> None:
    def run() -> None:
        try:
            def progress_callback(phase: str, current: int, total: int | None, message: str) -> None:
                with _DUPLICATE_JOBS_LOCK:
                    job = _DUPLICATE_JOBS.get(job_id)
                    if not job:
                        return
                    job["phase"] = phase
                    job["current"] = current
                    job["total"] = total
                    job["message"] = message
                    job["progress_percent"] = _duplicate_progress_percent(phase, current, total)

            report = move_duplicate_files_by_signature(
                source_root=source_root,
                target_root=target_root,
                progress_callback=progress_callback,
            )

            payload = {
                "ok": True,
                "source_root": str(report.source_root),
                "target_root": str(report.target_root),
                "scanned_files": report.scanned_files,
                "duplicate_groups": report.duplicate_groups,
                "moved_files": report.moved_files,
                "moved_bytes": report.moved_bytes,
                "skipped_count": report.skipped_count,
                "message": (
                    f"Moved {report.moved_files} duplicate files to '{report.target_root}'. "
                    f"Scanned {report.scanned_files} files in {report.duplicate_groups} duplicate groups."
                ),
            }
            if report.skipped_count:
                payload["warning"] = (
                    f"Skipped {report.skipped_count} files due to access or file changes during scan."
                )

            with _DUPLICATE_JOBS_LOCK:
                job = _DUPLICATE_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "done"
                    job["progress_percent"] = 100
                    job["message"] = "Duplicate cleanup completed."
                    job["result"] = payload
                    job["updated_at"] = time.time()
        except Exception as exc:  # broad catch to keep job state visible to UI
            with _DUPLICATE_JOBS_LOCK:
                job = _DUPLICATE_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "error"
                    job["progress_percent"] = 100
                    job["message"] = str(exc)
                    job["error"] = str(exc)
                    job["updated_at"] = time.time()

    thread = threading.Thread(target=run, name=f"duplicate-job-{job_id}", daemon=True)
    thread.start()


def _similar_progress_percent(phase: str, current: int, total: int | None) -> int:
    if phase == "collecting":
        if total and total > 0:
            return 5 + int((current / total) * 40)
        return 15
    if phase == "comparing":
        if total and total > 0:
            return 45 + int((current / total) * 54)
        return 60
    if phase in {"done", "error"}:
        return 100
    return 5


def _start_similar_files_job(job_id: str, root_folder: Path, threshold: float) -> None:
    def run() -> None:
        try:
            def progress_callback(phase: str, current: int, total: int | None, message: str) -> None:
                with _SIMILAR_JOBS_LOCK:
                    job = _SIMILAR_JOBS.get(job_id)
                    if not job:
                        return
                    job["phase"] = phase
                    job["current"] = current
                    job["total"] = total
                    job["message"] = message
                    job["progress_percent"] = _similar_progress_percent(phase, current, total)

            report = find_similar_spreadsheet_files(
                root=root_folder,
                threshold=threshold,
                progress_callback=progress_callback,
            )
            matches_payload = [
                {
                    "file_a": str(match.file_a),
                    "file_b": str(match.file_b),
                    "overall_similarity_pct": round(match.overall_similarity * 100, 2),
                    "sha256_hex": match.sha256_hex,
                }
                for match in report.matches[:100]
            ]
            payload = {
                "ok": True,
                "root": str(report.root),
                "threshold_pct": round(report.threshold * 100, 2),
                "scanned_files": report.scanned_files,
                "spreadsheet_files": report.spreadsheet_files,
                "skipped_count": report.skipped_count,
                "match_count": len(report.matches),
                "matches": matches_payload,
                "message": (
                    f"Found {len(report.matches)} identical spreadsheet pairs (SHA-256) "
                    f"at or above {round(report.threshold * 100, 2)}% match; "
                    f"listing only, no files moved."
                ),
            }
            if report.skipped_count:
                payload["warning"] = (
                    f"Skipped {report.skipped_count} files due to read errors."
                )
            with _SIMILAR_JOBS_LOCK:
                job = _SIMILAR_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "done"
                    job["progress_percent"] = 100
                    job["message"] = "Similar files scan completed."
                    job["result"] = payload
                    job["updated_at"] = time.time()
        except Exception as exc:
            with _SIMILAR_JOBS_LOCK:
                job = _SIMILAR_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "error"
                    job["progress_percent"] = 100
                    job["message"] = str(exc)
                    job["error"] = str(exc)
                    job["updated_at"] = time.time()

    thread = threading.Thread(target=run, name=f"similar-files-job-{job_id}", daemon=True)
    thread.start()


def _similar_to_ref_progress_percent(phase: str, current: int, total: int | None) -> int:
    if phase == "profiling":
        return 10 if current >= 1 else 5
    if phase == "collecting":
        if total and total > 0:
            return 12 + int((current / total) * 28)
        return 20
    if phase == "comparing":
        if total and total > 0:
            return 40 + int((current / total) * 55)
        return 55
    if phase in {"done", "error"}:
        return 100
    return 5


def _start_similar_to_reference_job(
    job_id: str, reference_file: Path, scan_folder: Path, threshold: float
) -> None:
    def run() -> None:
        try:

            def progress_callback(
                phase: str, current: int, total: int | None, message: str
            ) -> None:
                with _SIMILAR_REF_JOBS_LOCK:
                    job = _SIMILAR_REF_JOBS.get(job_id)
                    if not job:
                        return
                    job["phase"] = phase
                    job["current"] = current
                    job["total"] = total
                    job["message"] = message
                    job["progress_percent"] = _similar_to_ref_progress_percent(
                        phase, current, total
                    )

            report = find_similar_to_reference_file(
                reference_file=reference_file,
                root=scan_folder,
                threshold=threshold,
                progress_callback=progress_callback,
            )
            results = [
                {
                    "path": str(
                        match.file_b
                        if match.file_a.resolve() == report.reference_file.resolve()
                        else match.file_a
                    ),
                    "overall_similarity_pct": round(match.overall_similarity * 100, 2),
                    "sha256_hex": match.sha256_hex,
                }
                for match in report.matches
            ]
            payload = {
                "ok": True,
                "reference_file": str(report.reference_file),
                "reference_name": report.reference_file.name,
                "scan_folder": str(report.root),
                "threshold_pct": round(report.threshold * 100, 2),
                "scanned_files": report.scanned_files,
                "spreadsheet_files": report.spreadsheet_files,
                "skipped_count": report.skipped_count,
                "match_count": len(report.matches),
                "matches": results,
                "message": (
                    f"Found {len(report.matches)} files with identical bytes to "
                    f"'{report.reference_file.name}' (SHA-256), at or above "
                    f"{round(report.threshold * 100, 2)}% match threshold."
                ),
            }
            if report.skipped_count:
                payload["warning"] = (
                    f"Skipped {report.skipped_count} files due to read errors."
                )

            with _SIMILAR_REF_JOBS_LOCK:
                job = _SIMILAR_REF_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "done"
                    job["progress_percent"] = 100
                    job["message"] = "Scan completed."
                    job["result"] = payload
                    job["updated_at"] = time.time()
        except Exception as exc:
            with _SIMILAR_REF_JOBS_LOCK:
                job = _SIMILAR_REF_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "error"
                    job["progress_percent"] = 100
                    job["message"] = str(exc)
                    job["error"] = str(exc)
                    job["updated_at"] = time.time()

    thread = threading.Thread(
        target=run, name=f"similar-to-ref-job-{job_id}", daemon=True
    )
    thread.start()


def _excel_import_progress_percent(
    phase: str, current: int, total: int | None
) -> int:
    if phase == "reading":
        return 8
    if phase == "preparing":
        return 20
    if phase == "inserting":
        if total and total > 0:
            return min(99, 20 + int(79 * current / total))
        return 45
    if phase == "done":
        return 100
    return 12


def _start_excel_import_job(
    job_id: str,
    path: Path,
    sheet_name: str,
    postgres_db: str,
    table_name: str,
    filter_triples: list[tuple[str, str]] | None = None,
    selected_headers: list[str] | None = None,
) -> None:
    def run() -> None:
        try:

            def progress_callback(
                phase: str, current: int, total: int | None, message: str
            ) -> None:
                with _EXCEL_IMPORT_JOBS_LOCK:
                    job = _EXCEL_IMPORT_JOBS.get(job_id)
                    if not job:
                        return
                    job["phase"] = phase
                    job["current"] = current
                    job["total"] = total
                    job["message"] = message
                    job["progress_percent"] = _excel_import_progress_percent(
                        phase, current, total
                    )
                    job["updated_at"] = time.time()

            result = import_sheet_to_postgres(
                file_path=path,
                sheet_name=sheet_name,
                postgres_db=postgres_db,
                table_name=table_name,
                filter_triples=filter_triples or [],
                progress_callback=progress_callback,
                selected_headers=selected_headers,
            )
            with _EXCEL_IMPORT_JOBS_LOCK:
                job = _EXCEL_IMPORT_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "done"
                    job["progress_percent"] = 100
                    job["message"] = "Import completed."
                    job["result"] = result
                    job["updated_at"] = time.time()
        except Exception as exc:  # broad catch to keep job state visible to UI
            with _EXCEL_IMPORT_JOBS_LOCK:
                job = _EXCEL_IMPORT_JOBS.get(job_id)
                if job:
                    job["done"] = True
                    job["phase"] = "error"
                    job["progress_percent"] = 100
                    job["message"] = str(exc)
                    job["error"] = str(exc)
                    job["updated_at"] = time.time()

    thread = threading.Thread(
        target=run, name=f"excel-import-{job_id}", daemon=True
    )
    thread.start()


def _is_truthy_form_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _excel_import_mapping_warning(check: dict) -> str:
    missing = check.get("missing_in_table") or []
    table_only = check.get("table_only_columns") or []
    parts: list[str] = []
    if missing:
        parts.append(
            "Selected Excel columns missing in destination table: "
            + ", ".join(missing[:12])
            + ("ΓÇª" if len(missing) > 12 else "")
            + "."
        )
    if table_only:
        parts.append(
            "Destination table columns not present in selected Excel columns: "
            + ", ".join(table_only[:12])
            + ("ΓÇª" if len(table_only) > 12 else "")
            + "."
        )
    if not parts:
        return ""
    return "Column mismatch detected. " + " ".join(parts)

