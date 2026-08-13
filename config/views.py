from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, F, IntegerField, Min, Q, Sum, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from pathlib import Path
import threading
import time
import uuid

from hr.teams.models import (
    TeamMember,
)
from utilities.delete_duplicate_files import move_duplicate_files_by_signature
from utilities.delete_empty_folders import choose_root_folder, delete_empty_folders_under
from utilities.file_content_search import scan_folder_for_phrase
from utilities.move_files_to_fy_folder import move_direct_files_to_fy_folders
from utilities.move_files_by_name_contains import move_direct_files_name_contains
from utilities.rename_files_by_content_date import rename_direct_files_by_content_date
from utilities.rename_date_prefix_files import rename_direct_files_date_prefix
from utilities.rename_files_based_on_text import rename_direct_files_by_text
from utilities.similar_files import (
    choose_spreadsheet_file,
    find_similar_spreadsheet_files,
    find_similar_to_reference_file,
)
from utilities.excel_to_postgres import (
    choose_excel_file,
    create_public_table_from_schema_sheet,
    inspect_import_column_mapping,
    import_sheet_to_postgres,
    list_sheet_names,
    read_sheet_headers_only,
)
from utilities.pg_row_delete import (
    delete_rows_public,
    list_database_names,
    list_public_tables,
    list_table_columns,
    summarize_public_table_group_by,
    test_pg_connection,
)

from engagements.models import Engagement, STATUS_IN_PROGRESS, STATUS_SCHEDULED
from hr.teams.models import TeamMember

from .forms import SalesLedgerSettingsForm, SmtpMailSettingsForm, UserTodoForm

_DUPLICATE_JOBS_LOCK = threading.Lock()
_DUPLICATE_JOBS: dict[str, dict] = {}
_SIMILAR_JOBS_LOCK = threading.Lock()
_SIMILAR_JOBS: dict[str, dict] = {}
_SIMILAR_REF_JOBS_LOCK = threading.Lock()
_SIMILAR_REF_JOBS: dict[str, dict] = {}
_EXCEL_IMPORT_JOBS_LOCK = threading.Lock()
_EXCEL_IMPORT_JOBS: dict[str, dict] = {}

MODULE_ENGAGEMENTS = "module_engagements"
MODULE_SETUP = "module_setup"
MODULE_TOOLS = "module_tools"


def _has_module_access(user, module_group_name: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=module_group_name).exists()


def _engagement_queryset_for_user(user):
    qs = Engagement.objects.all()
    if user.is_superuser:
        return qs
    if not _has_module_access(user, MODULE_ENGAGEMENTS):
        return qs.none()
    team_member = TeamMember.objects.filter(user=user).values("pk")[:1]
    return qs.filter(
        Q(team_assignments__team_member_id__in=team_member)
        | Q(divisions__team_assignments__team_member_id__in=team_member)
        | Q(work_areas__team_assignments__team_member_id__in=team_member)
    ).distinct()


def _home_work_list_rows(user, request=None):
    """
    Rows for the home work list (engagements the user may access):

    1. Every **open** engagement-level or division-level **schedule line** (period with no
       ``actual_finish``).
    2. Every **engagement-level** and **division-level work area** on **Scheduled** or **In
       progress** engagements that does **not** already have an open schedule line (so
       timers and schedules are reachable even before period rows exist).
    3. A single **engagement** fallback row only when that engagement still has no period
       rows and **no** work areas at all.

    Open period rows are included for any engagement status (as long as the user can see
    the engagement). Bare work-area rows are limited to Scheduled / In progress to avoid
    listing every area on completed engagements.
    """
    import datetime

    from engagements.models import (
        DivisionWorkArea,
        DivisionWorkAreaPeriod,
        EngagementWorkArea,
        EngagementWorkAreaPeriod,
    )

    eng_qs = _engagement_queryset_for_user(user)
    if request is not None:
        from engagements.session_context import filter_engagement_queryset

        eng_qs = filter_engagement_queryset(eng_qs, request, user)
    rows = []
    ew_ids_with_open_period: set[int] = set()
    dw_ids_with_open_period: set[int] = set()

    for p in (
        EngagementWorkAreaPeriod.objects.filter(
            actual_finish__isnull=True,
            work_area__engagement__in=eng_qs,
        )
        .select_related(
            "work_area",
            "work_area__engagement",
            "work_area__engagement__client",
            "work_area__engagement__fiscal_year",
            "work_area__engagement__service",
        )
        .iterator()
    ):
        ew_ids_with_open_period.add(p.work_area_id)
        e = p.work_area.engagement
        sort_date = p.planned_finish or p.planned_start
        rows.append(
            {
                "kind": "ew_period",
                "engagement": e,
                "work_area": p.work_area,
                "label": p.work_area.work_area_name,
                "planned_finish": p.planned_finish,
                "sort_date": sort_date,
                "work_area_sort_key": p.work_area.sort_order,
            }
        )

    for p in (
        DivisionWorkAreaPeriod.objects.filter(
            actual_finish__isnull=True,
            work_area__division__engagement__in=eng_qs,
        )
        .select_related(
            "work_area",
            "work_area__division",
            "work_area__division__engagement",
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
        )
        .iterator()
    ):
        dw_ids_with_open_period.add(p.work_area_id)
        e = p.work_area.division.engagement
        div = p.work_area.division
        sort_date = p.planned_finish or p.planned_start
        rows.append(
            {
                "kind": "dw_period",
                "engagement": e,
                "division": div,
                "work_area": p.work_area,
                "label": f"{div.division_name} · {p.work_area.work_area_name}",
                "planned_finish": p.planned_finish,
                "sort_date": sort_date,
                "work_area_sort_key": p.work_area.sort_order,
            }
        )

    max_sort = datetime.date(9999, 12, 31)
    sched_or_in_progress = eng_qs.filter(
        status__in=[STATUS_SCHEDULED, STATUS_IN_PROGRESS]
    )

    for wa in (
        EngagementWorkArea.objects.filter(engagement__in=sched_or_in_progress)
        .exclude(pk__in=ew_ids_with_open_period)
        .select_related(
            "engagement",
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .iterator()
    ):
        e = wa.engagement
        rows.append(
            {
                "kind": "ew_area",
                "engagement": e,
                "work_area": wa,
                "label": wa.work_area_name,
                "planned_finish": None,
                "sort_date": max_sort,
                "work_area_sort_key": wa.sort_order,
            }
        )

    for wa in (
        DivisionWorkArea.objects.filter(division__engagement__in=sched_or_in_progress)
        .exclude(pk__in=dw_ids_with_open_period)
        .select_related(
            "division",
            "division__engagement",
            "division__engagement__client",
            "division__engagement__fiscal_year",
            "division__engagement__service",
        )
        .iterator()
    ):
        div = wa.division
        e = div.engagement
        rows.append(
            {
                "kind": "dw_area",
                "engagement": e,
                "division": div,
                "work_area": wa,
                "label": f"{div.division_name} · {wa.work_area_name}",
                "planned_finish": None,
                "sort_date": max_sort,
                "work_area_sort_key": wa.sort_order,
            }
        )

    covered_engagement_ids = {r["engagement"].pk for r in rows}

    for eng in (
        sched_or_in_progress.annotate(
            earliest_planned_finish=Min("schedules__planned_finish")
        ).select_related("client", "fiscal_year", "service")
    ):
        if eng.pk in covered_engagement_ids:
            continue
        sort_date = eng.earliest_planned_finish
        rows.append(
            {
                "kind": "engagement",
                "engagement": eng,
                "label": "Engagement (no work areas yet)",
                "planned_finish": eng.earliest_planned_finish,
                "sort_date": sort_date or max_sort,
                "work_area_sort_key": 10_000,
            }
        )

    rows.sort(
        key=lambda r: (
            r["sort_date"] or max_sort,
            r["engagement"].client.client_name,
            r["engagement"].fiscal_year.fy_no,
            r["engagement"].service.service_desc,
            r.get("work_area_sort_key", 0),
            r.get("label") or "",
        )
    )
    return rows


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
            + ("…" if len(missing) > 12 else "")
            + "."
        )
    if table_only:
        parts.append(
            "Destination table columns not present in selected Excel columns: "
            + ", ".join(table_only[:12])
            + ("…" if len(table_only) > 12 else "")
            + "."
        )
    if not parts:
        return ""
    return "Column mismatch detected. " + " ".join(parts)


def _user_todo_queryset(user):
    from .models import UserTodo

    return UserTodo.objects.filter(user=user).order_by(
        "is_completed",
        F("target_date").asc(nulls_last=True),
        "-created_on",
    )


@login_required
def my_todos(request):
    todos = _user_todo_queryset(request.user)
    return render(
        request,
        "config/my_todos.html",
        {
            "todos": todos,
            "today": timezone.localdate(),
        },
    )


@login_required
def my_todo_create(request):
    from .models import UserTodo

    if request.method == "POST":
        form = UserTodoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "Task added.")
            return redirect("my_todos")
    else:
        form = UserTodoForm()
    return render(request, "config/my_todo_form.html", {"form": form, "todo": None})


@login_required
def my_todo_edit(request, pk: int):
    from .models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    if request.method == "POST":
        form = UserTodoForm(request.POST, instance=todo)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated.")
            return redirect("my_todos")
    else:
        form = UserTodoForm(instance=todo)
    return render(request, "config/my_todo_form.html", {"form": form, "todo": todo})


@login_required
@require_POST
def my_todo_delete(request, pk: int):
    from .models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    todo.delete()
    messages.success(request, "Task removed.")
    return redirect("my_todos")


@login_required
@require_POST
def my_todo_toggle(request, pk: int):
    from .models import UserTodo

    todo = get_object_or_404(UserTodo, pk=pk, user=request.user)
    todo.is_completed = not todo.is_completed
    todo.save(update_fields=["is_completed", "updated_on"])
    messages.success(
        request, "Marked complete." if todo.is_completed else "Reopened task."
    )
    return redirect("my_todos")


def home(request):
    context = {}
    if request.user.is_authenticated:
        can_engagements = _has_module_access(request.user, MODULE_ENGAGEMENTS)
        can_setup = _has_module_access(request.user, MODULE_SETUP)
        can_tools = _has_module_access(request.user, MODULE_TOOLS)
        context["can_use_engagements"] = can_engagements
        context["can_use_setup"] = can_setup
        context["can_use_tools"] = can_tools
        if can_engagements:
            from engagements.views import (
                _active_time_session_for_user,
                _timer_scope_dict,
            )

            context["active_timer_scope"] = _timer_scope_dict(
                _active_time_session_for_user(request.user)
            )
            context["home_work_list_rows"] = _home_work_list_rows(
                request.user, request=request
            )
    return render(request, "home.html", context)


@login_required
def admin_technical_data_flow(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Only admins can view this document.")
    doc_path = Path(settings.BASE_DIR) / "TECHNICAL_DATA_FLOW.md"
    try:
        doc_text = doc_path.read_text(encoding="utf-8")
    except OSError:
        doc_text = "TECHNICAL_DATA_FLOW.md was not found."
    return render(
        request,
        "admin/technical_data_flow.html",
        {"doc_text": doc_text, "doc_path": doc_path.name},
    )


@login_required
def setup(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    return render(request, "setup.html")


@login_required
def gl_hub(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("You need Setup access to open the GL hub.")
    return render(request, "gl/gl_hub.html")


def _calendar_months_in_fiscal_year(fy):
    """Each calendar month overlapping ``fy`` as first-of-month date, last day, and label."""
    import calendar
    from datetime import date

    months = []
    cur = date(fy.start_date.year, fy.start_date.month, 1)
    while cur <= fy.end_date:
        last = calendar.monthrange(cur.year, cur.month)[1]
        pend = date(cur.year, cur.month, last)
        months.append(
            {
                "period_from": cur,
                "period_to": pend,
                "label": cur.strftime("%b %Y"),
            }
        )
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


@login_required
def gl_trial_balance(request):
    """GL trial balance: FY from GL rules, or ``tb_table_month`` for one month or YTD cumulative."""
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("You need Setup access to view the GL trial balance.")
    from decimal import Decimal

    from gl.fiscal_years.models import FiscalYear
    from gl.journal.models import TbTableMonth
    from gl.journal.trial_balance_report import build_gl_trial_balance_rows

    from .models import ChartOfAccount

    today = timezone.localdate()
    fiscal_years = list(FiscalYear.objects.all().order_by("-fy_no"))
    current_fy = None
    for fy in fiscal_years:
        if fy.start_date <= today <= fy.end_date:
            current_fy = fy
            break

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    month_param = (request.GET.get("month") or "").strip()
    selected_month_from = None
    month_label = ""
    if month_param and selected_fy is not None:
        parsed = parse_date(month_param)
        if parsed is not None:
            for m in _calendar_months_in_fiscal_year(selected_fy):
                if m["period_from"] == parsed:
                    selected_month_from = parsed
                    month_label = m["label"]
                    break

    month_options = (
        _calendar_months_in_fiscal_year(selected_fy) if selected_fy is not None else []
    )

    fy_months_json: dict[str, list[dict[str, str]]] = {}
    for fy in fiscal_years:
        fy_months_json[str(fy.pk)] = [
            {
                "value": m["period_from"].isoformat(),
                "label": (
                    f"{m['label']} ({m['period_from'].isoformat()} to {m['period_to'].isoformat()})"
                ),
            }
            for m in _calendar_months_in_fiscal_year(fy)
        ]

    submitted = request.GET.get("fy") is not None
    # YTD default on: absent param or last ytd=1 wins over hidden ytd=0 when checkbox checked.
    tb_month_ytd = request.GET.get("ytd") != "0"

    tb_rows: list[dict] = []
    total_dr = Decimal("0")
    total_cr = Decimal("0")
    balanced = True
    use_tb_table_month = False
    if submitted and selected_fy is not None:
        if selected_month_from is not None:
            use_tb_table_month = True
            first_m = selected_fy.start_date.replace(day=1)
            if tb_month_ytd:
                agg = (
                    TbTableMonth.objects.filter(
                        fiscal_year=selected_fy,
                        period_from__gte=first_m,
                        period_from__lte=selected_month_from,
                    )
                    .values("account_code")
                    .annotate(total=Sum("amount"))
                    .order_by("account_code")
                )
                codes = [row["account_code"] for row in agg]
            else:
                qs = (
                    TbTableMonth.objects.filter(
                        fiscal_year=selected_fy, period_from=selected_month_from
                    )
                    .order_by("account_code")
                )
                codes = list(qs.values_list("account_code", flat=True))
                agg = [{"account_code": r.account_code, "total": r.amount} for r in qs]
            name_by_code = {
                c.account_code: c.account_name.strip()
                for c in ChartOfAccount.objects.filter(account_code__in=codes)
            }
            for row in agg:
                amt = row["total"]
                if amt is None:
                    continue
                amt = Decimal(str(amt))
                if amt == 0:
                    continue
                if amt > 0:
                    dr, cr = amt, None
                    total_dr += amt
                else:
                    dr, cr = None, -amt
                    total_cr += -amt
                tb_rows.append(
                    {
                        "account_name": name_by_code.get(
                            row["account_code"], "Unmapped account"
                        ),
                        "account_code": row["account_code"],
                        "debit": dr,
                        "credit": cr,
                    }
                )
            balanced = abs(total_dr - total_cr) <= Decimal("0.01")
        else:
            tb_rows, total_dr, total_cr = build_gl_trial_balance_rows(selected_fy)
            balanced = abs(total_dr - total_cr) <= Decimal("0.01")

    return render(
        request,
        "gl/gl_trial_balance.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "month_options": month_options,
            "selected_month_param": month_param if selected_month_from else "",
            "selected_month_from": selected_month_from,
            "month_label": month_label,
            "report_submitted": submitted,
            "tb_rows": tb_rows,
            "total_dr": total_dr,
            "total_cr": total_cr,
            "tb_balanced": balanced,
            "use_tb_table_month": use_tb_table_month,
            "tb_month_ytd": tb_month_ytd,
            "fy_months_json": fy_months_json,
        },
    )


@login_required
def sales_ledger_settings(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    from .models import SalesLedgerSettings

    instance = SalesLedgerSettings.get_solo()
    if request.method == "POST":
        form = SalesLedgerSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Sales ledger settings saved.")
            return redirect("sales_ledger_settings")
    else:
        form = SalesLedgerSettingsForm(instance=instance)
    return render(
        request,
        "setup/sales_ledger_settings.html",
        {"form": form},
    )


def setup_mail_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can edit mail settings.")

    from .models import SmtpMailSettings

    instance = SmtpMailSettings.get_solo()
    if request.method == "POST":
        form = SmtpMailSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved settings.")
            return redirect("setup_mail_settings")
    else:
        form = SmtpMailSettingsForm(instance=instance)
    return render(
        request,
        "config/mail_settings.html",
        {"form": form},
    )


@login_required
def data_utilities(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    return render(request, "data_utilities.html")


@login_required
def tools_utilities(request):
    """Hub for secondary tools: to-do list, file/folder utilities, data utilities."""
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    return render(request, "tools_utilities.html")


@login_required
def data_analysis(request):
    d = settings.DATABASES["default"]
    return render(
        request,
        "data_analysis.html",
        {
            "default_host": d.get("HOST") or "127.0.0.1",
            "default_port": str(d.get("PORT") or "5432"),
            "default_user": d.get("USER") or "postgres",
            "default_db": d.get("NAME") or "",
        },
    )


@login_required
@require_POST
def data_analysis_summary_json(request):
    """GROUP BY label columns; SUM value columns on a public table."""
    try:
        p = _pg_row_delete_conn_params_from_post(request)
        table = (request.POST.get("table_name") or "").strip()
        labels = [x.strip() for x in request.POST.getlist("label_column") if x.strip()]
        values = [x.strip() for x in request.POST.getlist("value_column") if x.strip()]
        result = summarize_public_table_group_by(
            **p,
            table_name=table,
            label_columns=labels,
            value_columns=values,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, **result})


@login_required
def data_create_table(request):
    d = settings.DATABASES["default"]
    excel_path = request.session.get("data_create_table_excel_path", "")
    return render(
        request,
        "data_create_table.html",
        {
            "excel_path": excel_path,
            "default_host": d.get("HOST") or "127.0.0.1",
            "default_port": str(d.get("PORT") or "5432"),
            "default_user": d.get("USER") or "postgres",
            "default_db": d.get("NAME") or "",
        },
    )


@login_required
@require_POST
def select_create_table_excel_file(request):
    try:
        path = choose_excel_file()
    except RuntimeError:
        messages.error(
            request,
            "Could not open file picker. Run on a machine with desktop access.",
        )
        return redirect("data_create_table")

    if path is None:
        messages.info(request, "File selection cancelled.")
        return redirect("data_create_table")

    request.session["data_create_table_excel_path"] = str(path.resolve())
    messages.success(request, f"Selected: {path.name}")
    return redirect("data_create_table")


@login_required
@require_GET
def create_table_sheets_json(request):
    raw = request.session.get("data_create_table_excel_path", "")
    if not raw:
        return JsonResponse({"ok": False, "message": "No file selected."}, status=400)
    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)
    try:
        names = list_sheet_names(path)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "sheets": names})


@login_required
@require_POST
def create_table_run(request):
    """CREATE TABLE from Excel schema sheet using explicit connection parameters."""
    try:
        p = _pg_row_delete_conn_params_from_post(request)
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    raw = request.session.get("data_create_table_excel_path") or (
        request.POST.get("excel_path") or ""
    ).strip()
    sheet_name = (request.POST.get("sheet_name") or "").strip()
    table_name = (request.POST.get("table_name") or "").strip()

    if not raw:
        return JsonResponse({"ok": False, "message": "Select an Excel file first."}, status=400)
    if not sheet_name:
        return JsonResponse({"ok": False, "message": "Select a sheet."}, status=400)
    if not table_name:
        return JsonResponse({"ok": False, "message": "Enter the new table name."}, status=400)

    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)

    request.session["data_create_table_excel_path"] = str(path)

    try:
        result = create_public_table_from_schema_sheet(
            path,
            sheet_name,
            host=str(p["host"]),
            port=int(p["port"]),
            user=str(p["user"]),
            password=str(p["password"]),
            dbname=str(p["dbname"]),
            table_name=table_name,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    return JsonResponse({"ok": True, **result})


@login_required
def data_excel_import(request):
    excel_path = request.session.get("data_excel_import_path", "")
    d = settings.DATABASES["default"]
    pref_db = request.session.get("data_excel_import_postgres_db", "") or ""
    pref_sheet = request.session.get("data_excel_import_sheet_name", "") or ""
    pref_table = request.session.get("data_excel_import_table_name", "") or ""
    pref_cols = request.session.get("data_excel_import_selected_headers", []) or []
    initial_db = pref_db or (d.get("NAME") or "")
    return render(
        request,
        "data_excel_import.html",
        {
            "excel_path": excel_path,
            "default_db": d.get("NAME") or "",
            "initial_postgres_db": initial_db,
            "initial_sheet_name": pref_sheet,
            "initial_table_name": pref_table,
            "initial_selected_headers": pref_cols,
        },
    )


@login_required
@require_POST
def select_excel_import_file(request):
    retained_db = (request.POST.get("retain_postgres_db") or "").strip()
    retained_sheet = (request.POST.get("retain_sheet_name") or "").strip()
    retained_table = (request.POST.get("retain_table_name") or "").strip()
    retained_cols = [
        x.strip() for x in request.POST.getlist("retain_selected_column") if x.strip()
    ]
    _save_excel_import_preferences(
        request,
        postgres_db=retained_db,
        sheet_name=retained_sheet,
        table_name=retained_table,
        selected_headers=retained_cols,
    )

    try:
        path = choose_excel_file()
    except RuntimeError:
        messages.error(
            request,
            "Could not open file picker. Run on a machine with desktop access.",
        )
        return redirect("data_excel_import")

    if path is None:
        messages.info(request, "File selection cancelled.")
        return redirect("data_excel_import")

    request.session["data_excel_import_path"] = str(path.resolve())
    messages.success(request, f"Selected: {path.name}")
    return redirect("data_excel_import")


@login_required
@require_GET
def excel_import_sheets_json(request):
    raw = request.session.get("data_excel_import_path", "")
    if not raw:
        return JsonResponse({"ok": False, "message": "No file selected."}, status=400)
    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)
    try:
        names = list_sheet_names(path)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "sheets": names})


@login_required
@require_GET
def excel_import_headers_json(request):
    raw = request.session.get("data_excel_import_path", "")
    sheet = (request.GET.get("sheet") or "").strip()
    if not raw:
        return JsonResponse({"ok": False, "message": "No file selected."}, status=400)
    if not sheet:
        return JsonResponse({"ok": False, "message": "Sheet name required."}, status=400)
    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)
    try:
        headers = read_sheet_headers_only(path, sheet)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "headers": headers})


@login_required
@require_POST
def excel_import_match_report(request):
    """Return Excel ↔ PostgreSQL column mapping and types without importing."""
    raw = request.session.get("data_excel_import_path", "") or (
        request.POST.get("excel_path") or ""
    ).strip()
    sheet_name = (request.POST.get("sheet_name") or "").strip()
    postgres_db = (request.POST.get("postgres_db") or "").strip()
    table_name = (request.POST.get("table_name") or "").strip()

    raw_sel = [x.strip() for x in request.POST.getlist("selected_column") if x.strip()]
    selected_headers = raw_sel if raw_sel else None

    if not raw:
        return JsonResponse(
            {"ok": False, "message": "Select an Excel file first."}, status=400
        )
    if not sheet_name:
        return JsonResponse({"ok": False, "message": "Select a sheet."}, status=400)
    if not postgres_db:
        return JsonResponse(
            {"ok": False, "message": "Select a PostgreSQL database."},
            status=400,
        )
    if not table_name:
        return JsonResponse(
            {"ok": False, "message": "Enter the destination table name."},
            status=400,
        )

    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)

    request.session["data_excel_import_path"] = str(path)

    try:
        report = inspect_import_column_mapping(
            file_path=path,
            sheet_name=sheet_name,
            postgres_db=postgres_db,
            table_name=table_name,
            selected_headers=selected_headers,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    return JsonResponse({"ok": True, "report": report})


@login_required
@require_POST
def excel_import_run(request):
    raw = request.session.get("data_excel_import_path", "") or (
        request.POST.get("excel_path") or ""
    ).strip()
    sheet_name = (request.POST.get("sheet_name") or "").strip()
    postgres_db = (request.POST.get("postgres_db") or "").strip()
    table_name = (request.POST.get("table_name") or "").strip()

    if not raw:
        messages.error(request, "Select an Excel file first.")
        return redirect("data_excel_import")
    if not sheet_name:
        messages.error(request, "Select a sheet.")
        return redirect("data_excel_import")
    if not postgres_db:
        messages.error(request, "Select a PostgreSQL database.")
        return redirect("data_excel_import")
    if not table_name:
        messages.error(request, "Enter the destination table name.")
        return redirect("data_excel_import")

    path = Path(raw).expanduser()
    request.session["data_excel_import_path"] = str(path)

    raw_sel = [x.strip() for x in request.POST.getlist("selected_column") if x.strip()]
    selected_headers = raw_sel if raw_sel else None
    _save_excel_import_preferences(
        request,
        postgres_db=postgres_db,
        sheet_name=sheet_name,
        table_name=table_name,
        selected_headers=raw_sel,
    )
    confirm_mismatch = _is_truthy_form_value(
        (request.POST.get("confirm_mismatch") or "")
    )

    try:
        mapping_check = inspect_import_column_mapping(
            file_path=path,
            sheet_name=sheet_name,
            postgres_db=postgres_db,
            table_name=table_name,
            selected_headers=selected_headers,
        )
    except Exception as exc:
        messages.error(request, f"Import failed: {exc}")
        return redirect("data_excel_import")

    if not mapping_check.get("exact_match") and not confirm_mismatch:
        warn = _excel_import_mapping_warning(mapping_check)
        if not warn:
            warn = "Column mismatch detected between Excel and destination table."
        messages.error(request, f"{warn} Review columns and run import again.")
        return redirect("data_excel_import")

    try:
        result = import_sheet_to_postgres(
            file_path=path,
            sheet_name=sheet_name,
            postgres_db=postgres_db,
            table_name=table_name,
            filter_triples=None,
            selected_headers=selected_headers,
        )
    except Exception as exc:
        messages.error(request, f"Import failed: {exc}")
        return redirect("data_excel_import")

    extra = ""
    if result.get("columns_not_in_table"):
        extra = (
            f" Skipped columns not in the table: "
            f"{', '.join(result['columns_not_in_table'])}."
        )
    messages.success(
        request,
        (
            f"Imported {result['inserted']} row(s) into "
            f"{postgres_db}.public.{result['table_name']}."
            f"{extra}"
        ),
    )
    return redirect("data_excel_import")


@login_required
@require_POST
def excel_import_start(request):
    """Start Excel import in a background thread; poll ``excel_import_status`` for progress."""
    raw = request.session.get("data_excel_import_path", "") or (
        request.POST.get("excel_path") or ""
    ).strip()
    sheet_name = (request.POST.get("sheet_name") or "").strip()
    postgres_db = (request.POST.get("postgres_db") or "").strip()
    table_name = (request.POST.get("table_name") or "").strip()

    raw_sel = [x.strip() for x in request.POST.getlist("selected_column") if x.strip()]
    selected_headers = raw_sel if raw_sel else None
    _save_excel_import_preferences(
        request,
        postgres_db=postgres_db,
        sheet_name=sheet_name,
        table_name=table_name,
        selected_headers=raw_sel,
    )
    confirm_mismatch = _is_truthy_form_value(
        (request.POST.get("confirm_mismatch") or "")
    )

    if not raw:
        return JsonResponse(
            {"ok": False, "message": "Select an Excel file first."}, status=400
        )
    if not sheet_name:
        return JsonResponse({"ok": False, "message": "Select a sheet."}, status=400)
    if not postgres_db:
        return JsonResponse(
            {"ok": False, "message": "Select a PostgreSQL database."},
            status=400,
        )
    if not table_name:
        return JsonResponse(
            {"ok": False, "message": "Enter the destination table name."},
            status=400,
        )

    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)

    request.session["data_excel_import_path"] = str(path)

    try:
        mapping_check = inspect_import_column_mapping(
            file_path=path,
            sheet_name=sheet_name,
            postgres_db=postgres_db,
            table_name=table_name,
            selected_headers=selected_headers,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    if not mapping_check.get("exact_match") and not confirm_mismatch:
        warning = _excel_import_mapping_warning(mapping_check)
        if not warning:
            warning = "Column mismatch detected between Excel and destination table."
        return JsonResponse(
            {
                "ok": False,
                "needs_confirmation": True,
                "message": warning,
                "mapping_check": mapping_check,
            },
            status=409,
        )

    job_id = str(uuid.uuid4())
    with _EXCEL_IMPORT_JOBS_LOCK:
        _EXCEL_IMPORT_JOBS[job_id] = {
            "done": False,
            "phase": "queued",
            "current": 0,
            "total": None,
            "progress_percent": 5,
            "message": "Starting import…",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    _start_excel_import_job(
        job_id=job_id,
        path=path,
        sheet_name=sheet_name,
        postgres_db=postgres_db,
        table_name=table_name,
        filter_triples=None,
        selected_headers=selected_headers,
    )

    return JsonResponse(
        {"ok": True, "job_id": job_id, "message": "Import started."}
    )


@login_required
@require_GET
def excel_import_status(request, job_id):
    with _EXCEL_IMPORT_JOBS_LOCK:
        job = _EXCEL_IMPORT_JOBS.get(job_id)

    if not job:
        return JsonResponse({"ok": False, "message": "Job not found."}, status=404)

    payload = {
        "ok": True,
        "job_id": job_id,
        "done": job["done"],
        "phase": job["phase"],
        "current": job["current"],
        "total": job["total"],
        "progress_percent": job["progress_percent"],
        "message": job["message"],
    }
    if job.get("error"):
        payload["error"] = job["error"]
    if job.get("result"):
        res = dict(job["result"])
        ct = res.get("column_types")
        if ct is not None:
            res["column_types"] = [list(pair) for pair in ct]
        payload["result"] = res
    return JsonResponse(payload)


def _pg_row_delete_conn_params_from_post(request) -> dict[str, str | int]:
    port_raw = (request.POST.get("pg_port") or "").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("Port must be an integer.") from exc
    return {
        "host": (request.POST.get("pg_host") or "").strip(),
        "port": port,
        "user": (request.POST.get("pg_user") or "").strip(),
        "password": request.POST.get("pg_password") or "",
        "dbname": (request.POST.get("pg_dbname") or "").strip(),
    }


def _pg_conn_params_from_post_with_default_db(
    request, *, default_db: str = "postgres"
) -> dict[str, str | int]:
    """Like ``_pg_row_delete_conn_params_from_post`` but uses ``default_db`` when db name is empty."""
    port_raw = (request.POST.get("pg_port") or "").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("Port must be an integer.") from exc
    dbname = (request.POST.get("pg_dbname") or "").strip() or default_db
    return {
        "host": (request.POST.get("pg_host") or "").strip(),
        "port": port,
        "user": (request.POST.get("pg_user") or "").strip(),
        "password": request.POST.get("pg_password") or "",
        "dbname": dbname,
    }


def _resolve_table_name(tables: list[str], requested: str) -> str | None:
    req = (requested or "").strip()
    if not req:
        return None
    by_lower = {t.lower(): t for t in tables}
    return by_lower.get(req.lower())


@login_required
def data_pg_row_delete(request):
    d = settings.DATABASES["default"]
    return render(
        request,
        "data_pg_row_delete.html",
        {
            "default_host": d.get("HOST") or "127.0.0.1",
            "default_port": str(d.get("PORT") or "5432"),
            "default_user": d.get("USER") or "postgres",
            "default_db": d.get("NAME") or "",
        },
    )


@login_required
@require_POST
def pg_row_delete_test_json(request):
    try:
        p = _pg_row_delete_conn_params_from_post(request)
        info = test_pg_connection(**p)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "message": (
                f"Connection OK. Database {info['database']!r}, session user {info['user']!r}."
            ),
            "database": info["database"],
            "user": info["user"],
        }
    )


@login_required
@require_GET
def pg_list_databases_settings_json(request):
    """List databases using Django ``DATABASES['default']`` (same connection as Excel → PostgreSQL import)."""
    d = settings.DATABASES["default"]
    connect_dbname = (d.get("NAME") or "").strip() or "postgres"
    try:
        names = list_database_names(
            host=d.get("HOST") or "127.0.0.1",
            port=int(d.get("PORT") or 5432),
            user=d.get("USER") or "postgres",
            password=d.get("PASSWORD") or "",
            dbname=connect_dbname,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "databases": names})


@login_required
@require_POST
def pg_list_databases_json(request):
    """List databases visible to the user. Connects using ``pg_dbname`` or ``postgres`` if empty."""
    try:
        p = _pg_conn_params_from_post_with_default_db(request, default_db="postgres")
        names = list_database_names(
            host=str(p["host"]),
            port=int(p["port"]),
            user=str(p["user"]),
            password=str(p["password"]),
            dbname=str(p["dbname"]),
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "databases": names})


@login_required
@require_POST
def pg_row_delete_tables_json(request):
    try:
        p = _pg_row_delete_conn_params_from_post(request)
        tables = list_public_tables(**p)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "tables": tables})


@login_required
@require_POST
def pg_row_delete_columns_json(request):
    try:
        p = _pg_row_delete_conn_params_from_post(request)
        table = (request.POST.get("table_name") or "").strip()
        tables = list_public_tables(**p)
        resolved = _resolve_table_name(tables, table)
        if not resolved:
            return JsonResponse(
                {"ok": False, "message": "Unknown table. Choose a database and pick a table from the list."},
                status=400,
            )
        cols = list_table_columns(**p, table_name=resolved)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "columns": cols, "table_name": resolved})


@login_required
@require_POST
def pg_row_delete_execute(request):
    try:
        p = _pg_row_delete_conn_params_from_post(request)
        table = (request.POST.get("table_name") or "").strip()
        tables = list_public_tables(**p)
        resolved = _resolve_table_name(tables, table)
        if not resolved:
            return JsonResponse(
                {"ok": False, "message": "Unknown table. Choose a database and pick a table from the list."},
                status=400,
            )
        delete_all = (request.POST.get("delete_all") or "").strip() == "1"
        confirm = (request.POST.get("delete_all_confirm") or "").strip()
        filters: list[tuple[str, str, str]] = []
        for i in range(1, 4):
            c = (request.POST.get(f"filter{i}_col") or "").strip()
            o = (request.POST.get(f"filter{i}_op") or "").strip()
            v = request.POST.get(f"filter{i}_val")
            if v is None:
                v = ""
            if c or o or str(v).strip():
                filters.append((c, o, str(v)))
        result = delete_rows_public(
            **p,
            table_name=resolved,
            delete_all=delete_all,
            delete_all_confirm=confirm,
            filters=filters,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "deleted": result["deleted"],
            "table": result["table"],
            "database": result["database"],
            "message": (
                f"Deleted {result['deleted']} row(s) from "
                f"{result['database']!r}.public.{result['table']}."
            ),
        }
    )


@login_required
def utilities(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    selected_empty_folder = request.session.get("utilities_selected_folder", "")
    duplicate_source_folder = request.session.get("utilities_duplicate_source_folder", "")
    duplicate_target_folder = request.session.get("utilities_duplicate_target_folder", "")
    content_search_folder = request.session.get("utilities_content_search_folder", "")
    return render(
        request,
        "utilities.html",
        {
            "selected_empty_folder": selected_empty_folder,
            "duplicate_source_folder": duplicate_source_folder,
            "duplicate_target_folder": duplicate_target_folder,
            "content_search_folder": content_search_folder,
        },
    )


@login_required
def rename_files_utilities(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    rename_date_prefix_folder = request.session.get(
        "utilities_rename_date_prefix_folder", ""
    )
    rename_date_prefix_marker = request.session.get(
        "utilities_rename_date_prefix_marker", ""
    )
    existing_pattern = request.session.get("utilities_rename_existing_pattern", "")
    replacement_pattern = request.session.get(
        "utilities_rename_replacement_pattern", ""
    )
    rename_date_pattern_position = request.session.get(
        "utilities_rename_date_pattern_position", "leading"
    )
    rename_content_date_folder = request.session.get(
        "utilities_rename_content_date_folder", ""
    )
    rename_content_date_pattern = request.session.get(
        "utilities_rename_content_date_pattern", "dd-mm-yy"
    )
    rename_content_date_file_type = request.session.get(
        "utilities_rename_content_date_file_type", "all"
    )
    return render(
        request,
        "rename_files_utilities.html",
        {
            "rename_date_prefix_folder": rename_date_prefix_folder,
            "rename_date_prefix_marker": rename_date_prefix_marker,
            "existing_text_pattern": existing_pattern,
            "replacement_pattern": replacement_pattern,
            "rename_date_pattern_position": rename_date_pattern_position,
            "rename_text_folder": request.session.get("utilities_rename_text_folder", ""),
            "rename_content_date_folder": rename_content_date_folder,
            "rename_content_date_pattern": rename_content_date_pattern,
            "rename_content_date_file_type": rename_content_date_file_type,
        },
    )


@login_required
def rename_files_date_prefix_tool(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    rename_date_prefix_folder = request.session.get(
        "utilities_rename_date_prefix_folder", ""
    )
    rename_date_prefix_marker = request.session.get(
        "utilities_rename_date_prefix_marker", ""
    )
    existing_pattern = request.session.get("utilities_rename_existing_pattern", "YYDDMM")
    replacement_pattern = request.session.get(
        "utilities_rename_replacement_pattern", "YYYY DD MM"
    )
    rename_date_pattern_position = request.session.get(
        "utilities_rename_date_pattern_position", "leading"
    )
    return render(
        request,
        "rename_files_date_prefix_tool.html",
        {
            "rename_date_prefix_folder": rename_date_prefix_folder,
            "rename_date_prefix_marker": rename_date_prefix_marker,
            "existing_text_pattern": existing_pattern,
            "replacement_pattern": replacement_pattern,
            "rename_date_pattern_position": rename_date_pattern_position,
        },
    )


@login_required
def rename_files_text_tool(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    return render(
        request,
        "rename_files_text_tool.html",
        {
            "rename_text_folder": request.session.get("utilities_rename_text_folder", ""),
        },
    )


@login_required
def organize_files_utilities(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    move_to_fy_folder = request.session.get("utilities_move_to_fy_folder", "")
    move_name_search_folder = request.session.get("utilities_move_name_search_folder", "")
    move_name_target_folder = request.session.get("utilities_move_name_target_folder", "")
    return render(
        request,
        "organize_files_utilities.html",
        {
            "move_to_fy_folder": move_to_fy_folder,
            "move_name_search_folder": move_name_search_folder,
            "move_name_target_folder": move_name_target_folder,
        },
    )


@login_required
def audit_document_renaming_filing(request):
    """Audit and accounts document rules (Word, PDF, PPT, Excel); future log UI will use the same module."""
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    from utilities.audit_accounts_documents import (
        AUDIT_ACCOUNTS_EXTENSIONS,
        AUDIT_ACCOUNTS_FILE_CLASSES,
        FILING_RULES_AUDIT_ACCOUNTS,
        NAMING_RULES_AUDIT_ACCOUNTS,
        OUT_OF_SCOPE_NOTE,
    )

    return render(
        request,
        "audit_document_renaming_filing.html",
        {
            "file_classes": AUDIT_ACCOUNTS_FILE_CLASSES,
            "all_extensions": sorted(AUDIT_ACCOUNTS_EXTENSIONS),
            "naming_rules": NAMING_RULES_AUDIT_ACCOUNTS,
            "filing_rules": FILING_RULES_AUDIT_ACCOUNTS,
            "out_of_scope_note": OUT_OF_SCOPE_NOTE,
        },
    )


@login_required
def audit_document_triage(request):
    """Scan review folder by phrase per category, then move matches into sorted subfolders."""
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    from utilities.audit_document_triage import triage_categories_as_dicts

    source = request.session.get("utilities_audit_triage_source", "")
    dest_base = request.session.get("utilities_audit_triage_dest_base", "")
    return render(
        request,
        "audit_document_triage.html",
        {
            "categories": triage_categories_as_dicts(),
            "triage_source_folder": source,
            "triage_dest_base": dest_base,
        },
    )


@login_required
@require_POST
def select_audit_triage_source(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("audit_document_triage")

    if root_path is None:
        messages.info(request, "Folder selection cancelled.")
        return redirect("audit_document_triage")

    request.session["utilities_audit_triage_source"] = str(root_path)
    messages.success(request, f"Selected review folder: {root_path}")
    return redirect("audit_document_triage")


@login_required
@require_POST
def select_audit_triage_dest(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("audit_document_triage")

    if root_path is None:
        messages.info(request, "Destination selection cancelled.")
        return redirect("audit_document_triage")

    request.session["utilities_audit_triage_dest_base"] = str(root_path)
    messages.success(request, f"Selected destination base: {root_path}")
    return redirect("audit_document_triage")


@login_required
@require_POST
def audit_triage_scan(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        return JsonResponse({"ok": False, "message": "Forbidden."}, status=403)
    from pathlib import Path

    from utilities.audit_document_triage import triage_scan_folder

    folder = (request.POST.get("triage_source_folder") or "").strip()
    if not folder:
        folder = request.session.get("utilities_audit_triage_source", "")
    phrase = (request.POST.get("phrase") or "").strip()
    include_fn = request.POST.get("include_filename") in ("1", "true", "on", "yes")

    if not folder:
        return JsonResponse({"ok": False, "message": "Select a review folder first."}, status=400)
    if not phrase:
        return JsonResponse({"ok": False, "message": "Enter a search phrase."}, status=400)

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse({"ok": False, "message": f"Folder not found: {root_path}"}, status=400)

    request.session["utilities_audit_triage_source"] = str(root_path.resolve())
    try:
        report = triage_scan_folder(root_path, phrase, include_filename=include_fn)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": f"Search failed: {exc}"}, status=500)

    payload = {
        "ok": True,
        "matches": report.matches,
        "scanned_files": report.scanned_files,
        "skipped_files": report.skipped_files,
        "message": (
            f"Found {len(report.matches)} file(s). Scanned {report.scanned_files} file(s); "
            f"skipped {report.skipped_files} unsupported type(s)."
        ),
    }
    if report.errors:
        payload["warning"] = "; ".join(report.errors[:5])
        if len(report.errors) > 5:
            payload["warning"] += f" … +{len(report.errors) - 5} more."
    return JsonResponse(payload)


@login_required
@require_POST
def audit_triage_move(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        return JsonResponse({"ok": False, "message": "Forbidden."}, status=403)
    import json
    from pathlib import Path

    from utilities.audit_document_triage import AUDIT_TRIAGE_CATEGORIES, move_triage_matches

    scan_folder = (request.POST.get("triage_source_folder") or "").strip()
    if not scan_folder:
        scan_folder = request.session.get("utilities_audit_triage_source", "")
    dest_base = (request.POST.get("triage_dest_base") or "").strip()
    if not dest_base:
        dest_base = request.session.get("utilities_audit_triage_dest_base", "")
    folder_slug = (request.POST.get("folder_slug") or "").strip()
    raw_paths = request.POST.get("paths_json") or "[]"

    if not scan_folder:
        return JsonResponse({"ok": False, "message": "Select a review folder first."}, status=400)
    if not dest_base:
        return JsonResponse({"ok": False, "message": "Select a destination base folder first."}, status=400)
    if not folder_slug:
        return JsonResponse({"ok": False, "message": "Missing category folder."}, status=400)
    if not any(c.folder_slug == folder_slug for c in AUDIT_TRIAGE_CATEGORIES):
        return JsonResponse({"ok": False, "message": "Invalid category folder."}, status=400)

    try:
        paths = json.loads(raw_paths)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "Invalid paths payload."}, status=400)
    if not isinstance(paths, list):
        return JsonResponse({"ok": False, "message": "paths_json must be a JSON array."}, status=400)
    if len(paths) > 800:
        return JsonResponse({"ok": False, "message": "Too many paths (max 800)."}, status=400)

    scan_p = Path(scan_folder).expanduser()
    dest_p = Path(dest_base).expanduser()
    if not scan_p.exists() or not scan_p.is_dir():
        return JsonResponse({"ok": False, "message": f"Review folder not found: {scan_p}"}, status=400)
    if not dest_p.exists():
        try:
            dest_p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    if not dest_p.is_dir():
        return JsonResponse({"ok": False, "message": "Destination base is not a folder."}, status=400)

    request.session["utilities_audit_triage_source"] = str(scan_p.resolve())
    request.session["utilities_audit_triage_dest_base"] = str(dest_p.resolve())

    try:
        report = move_triage_matches(
            scan_root=scan_p,
            destination_base=dest_p,
            folder_slug=folder_slug,
            source_paths=[str(p) for p in paths],
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=500)

    dest_show = dest_p / folder_slug
    msg = f"Moved {report.moved_count} file(s) into {dest_show}."
    payload = {
        "ok": True,
        "moved_count": report.moved_count,
        "message": msg,
        "skipped": report.skipped_paths,
    }
    if report.skipped_paths:
        payload["warning"] = f"Skipped {len(report.skipped_paths)} path(s)."
    return JsonResponse(payload)


@login_required
def organize_files_fy_move_tool(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    move_to_fy_folder = request.session.get("utilities_move_to_fy_folder", "")
    return render(
        request,
        "organize_files_fy_move_tool.html",
        {
            "move_to_fy_folder": move_to_fy_folder,
        },
    )


def _similar_files_page_context(request, results=None, threshold="95"):
    reference_file = request.session.get("utilities_similar_reference_file", "")
    scan_folder = ""
    if reference_file:
        try:
            scan_folder = str(Path(reference_file).expanduser().resolve().parent)
        except OSError:
            scan_folder = str(Path(reference_file).expanduser().parent)
    return {
        "reference_file": reference_file,
        "scan_folder": scan_folder,
        "threshold": threshold,
        "results": results or [],
    }


@login_required
def similar_files_page(request):
    context = _similar_files_page_context(request)
    return render(request, "similar_files.html", context)


@login_required
@require_POST
def select_folder_for_delete_empty(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("utilities")

    if root_path is None:
        messages.info(request, "Folder selection cancelled.")
        return redirect("utilities")

    request.session["utilities_selected_folder"] = str(root_path)
    messages.success(request, f"Selected folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_duplicate_source_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("utilities")

    if root_path is None:
        messages.info(request, "Source folder selection cancelled.")
        return redirect("utilities")

    request.session["utilities_duplicate_source_folder"] = str(root_path)
    messages.success(request, f"Selected duplicate scan source folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_duplicate_target_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("utilities")

    if root_path is None:
        messages.info(request, "Target folder selection cancelled.")
        return redirect("utilities")

    request.session["utilities_duplicate_target_folder"] = str(root_path)
    messages.success(request, f"Selected duplicate target folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_content_search_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("utilities")

    if root_path is None:
        messages.info(request, "Content search folder selection cancelled.")
        return redirect("utilities")

    request.session["utilities_content_search_folder"] = str(root_path)
    messages.success(request, f"Selected folder for file content search: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_rename_date_prefix_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("rename_files_utilities")

    if root_path is None:
        messages.info(request, "Rename folder selection cancelled.")
        return redirect("rename_files_utilities")

    request.session["utilities_rename_date_prefix_folder"] = str(root_path)
    messages.success(request, f"Selected folder for YYMMDD prefix rename: {root_path}")
    return redirect("rename_files_utilities")


@login_required
@require_POST
def select_rename_text_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("rename_files_utilities")

    if root_path is None:
        messages.info(request, "Rename-text folder selection cancelled.")
        return redirect("rename_files_utilities")

    request.session["utilities_rename_text_folder"] = str(root_path)
    messages.success(request, f"Selected folder for text-based rename: {root_path}")
    return redirect("rename_files_utilities")


@login_required
@require_POST
def select_rename_content_date_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("rename_files_utilities")

    if root_path is None:
        messages.info(request, "Rename-by-content folder selection cancelled.")
        return redirect("rename_files_utilities")

    request.session["utilities_rename_content_date_folder"] = str(root_path)
    messages.success(request, f"Selected folder for content-date rename: {root_path}")
    return redirect("rename_files_utilities")


@login_required
@require_POST
def select_move_to_fy_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("organize_files_fy_move_tool")

    if root_path is None:
        messages.info(request, "FY move folder selection cancelled.")
        return redirect("organize_files_fy_move_tool")

    request.session["utilities_move_to_fy_folder"] = str(root_path)
    messages.success(request, f"Selected folder for FY move: {root_path}")
    return redirect("organize_files_fy_move_tool")


@login_required
@require_POST
def select_move_name_search_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("organize_files_utilities")

    if root_path is None:
        messages.info(request, "Search folder selection cancelled.")
        return redirect("organize_files_utilities")

    request.session["utilities_move_name_search_folder"] = str(root_path)
    messages.success(request, f"Selected search folder: {root_path}")
    return redirect("organize_files_utilities")


@login_required
@require_POST
def select_move_name_target_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("organize_files_utilities")

    if root_path is None:
        messages.info(request, "Target folder selection cancelled.")
        return redirect("organize_files_utilities")

    request.session["utilities_move_name_target_folder"] = str(root_path)
    messages.success(request, f"Selected target folder: {root_path}")
    return redirect("organize_files_utilities")


@login_required
@require_POST
def select_similar_files_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("utilities")

    if root_path is None:
        messages.info(request, "Similar files folder selection cancelled.")
        return redirect("utilities")

    request.session["utilities_similar_files_folder"] = str(root_path)
    messages.success(request, f"Selected similar files scan folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_similar_reference_file(request):
    try:
        file_path = choose_spreadsheet_file()
    except RuntimeError:
        messages.error(
            request,
            "Could not open file selector. Run this on a machine with desktop access.",
        )
        return redirect("similar_files_page")

    if file_path is None:
        messages.info(request, "Reference file selection cancelled.")
        return redirect("similar_files_page")

    request.session["utilities_similar_reference_file"] = str(file_path)
    messages.success(request, f"Selected reference file: {file_path.name}")
    return redirect("similar_files_page")


@login_required
@require_POST
def delete_empty_folders(request):
    selected_folder = (request.POST.get("selected_folder") or "").strip()
    if not selected_folder:
        selected_folder = request.session.get("utilities_selected_folder", "")
    if not selected_folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder first."},
            status=400,
        )

    root_path = Path(selected_folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_selected_folder"] = str(root_path)
    report = delete_empty_folders_under(root_path)
    response_payload = {
        "ok": True,
        "root": str(report.root),
        "scanned_count": report.scanned_count,
        "deleted_count": report.deleted_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Deleted {report.deleted_count} empty folders under '{report.root}'. "
            f"Scanned {report.scanned_count} folders."
        ),
    }
    if report.skipped_count:
        response_payload["warning"] = (
            f"Skipped {report.skipped_count} folders due to access or file changes "
            "during scan."
        )
    return JsonResponse(response_payload)


@login_required
@require_POST
def file_content_search(request):
    phrase = (request.POST.get("search_phrase") or "").strip()
    folder = (
        (request.POST.get("content_search_folder") or "").strip()
        or request.session.get("utilities_content_search_folder", "")
    )
    if not folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder to search first."},
            status=400,
        )
    if not phrase:
        return JsonResponse(
            {"ok": False, "message": "Enter a search phrase."},
            status=400,
        )

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_content_search_folder"] = str(root_path)
    try:
        report = scan_folder_for_phrase(root_path, phrase)
    except Exception as exc:
        return JsonResponse(
            {"ok": False, "message": f"Search failed: {exc}"},
            status=500,
        )
    match_count = len(report.matches)
    payload = {
        "ok": True,
        "matches": report.matches,
        "scanned_files": report.scanned_files,
        "skipped_files": report.skipped_files,
        "message": (
            f"Found {match_count} file(s) with a case-neutral match for the phrase "
            f"in the first {report.word_limit} words. Scanned {report.scanned_files} file(s); "
            f"skipped {report.skipped_files} unsupported types (e.g. .xlsb, legacy .doc/.ppt)."
        ),
    }
    if report.errors:
        payload["warning"] = "Some paths had errors: " + "; ".join(report.errors[:5])
        if len(report.errors) > 5:
            payload["warning"] += f" … and {len(report.errors) - 5} more."
    return JsonResponse(payload)


@login_required
@require_POST
def rename_date_prefix_files(request):
    folder = (
        (request.POST.get("rename_date_prefix_folder") or "").strip()
        or request.session.get("utilities_rename_date_prefix_folder", "")
    )
    marker = (request.POST.get("rename_date_prefix_marker") or "").strip()
    existing_pattern = (request.POST.get("existing_text_pattern") or "").strip()
    replacement_pattern = (request.POST.get("replacement_pattern") or "").strip()
    pos_raw = (request.POST.get("rename_date_pattern_position") or "leading").strip().lower()
    if pos_raw not in ("leading", "anywhere"):
        pos_raw = "leading"
    pattern_start_only = pos_raw != "anywhere"
    if not existing_pattern:
        return JsonResponse(
            {"ok": False, "message": "Enter Existing text pattern."},
            status=400,
        )
    if not replacement_pattern:
        return JsonResponse(
            {"ok": False, "message": "Enter Replacement pattern."},
            status=400,
        )
    if not folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder first."},
            status=400,
        )

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_rename_date_prefix_folder"] = str(root_path)
    request.session["utilities_rename_date_prefix_marker"] = marker
    request.session["utilities_rename_existing_pattern"] = existing_pattern
    request.session["utilities_rename_replacement_pattern"] = replacement_pattern
    request.session["utilities_rename_date_pattern_position"] = pos_raw
    try:
        report = rename_direct_files_date_prefix(
            root_path,
            trim_left_until=marker,
            existing_pattern=existing_pattern,
            replacement_pattern=replacement_pattern,
            pattern_start_only=pattern_start_only,
        )
    except ValueError as exc:
        return JsonResponse(
            {"ok": False, "message": str(exc)},
            status=400,
        )
    except OSError as exc:
        return JsonResponse(
            {"ok": False, "message": f"Rename failed: {exc}"},
            status=500,
        )

    payload = {
        "ok": True,
        "renamed_count": report.renamed_count,
        "scanned_files": report.scanned_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Renamed {report.renamed_count} file(s) in '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) without a valid date pattern match "
            "or due to naming conflicts/errors."
        )
    return JsonResponse(payload)


@login_required
@require_POST
def rename_files_based_on_text(request):
    folder = (
        (request.POST.get("rename_text_folder") or "").strip()
        or request.session.get("utilities_rename_text_folder", "")
    )
    identifier = (request.POST.get("file_name_text_identifier") or "").strip()
    criteria = (request.POST.get("rename_criteria") or "").strip()

    if not folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder first."},
            status=400,
        )

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_rename_text_folder"] = str(root_path)
    try:
        report = rename_direct_files_by_text(
            root_path,
            identifier=identifier,
            criteria=criteria,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except OSError as exc:
        return JsonResponse({"ok": False, "message": f"Rename failed: {exc}"}, status=500)

    payload = {
        "ok": True,
        "renamed_count": report.renamed_count,
        "scanned_files": report.scanned_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Renamed {report.renamed_count} file(s) in '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) where identifier not found "
            "or due to naming errors."
        )
    return JsonResponse(payload)


@login_required
@require_POST
def rename_files_by_content_date(request):
    folder = (
        (request.POST.get("rename_content_date_folder") or "").strip()
        or request.session.get("utilities_rename_content_date_folder", "")
    )
    date_search_pattern = (request.POST.get("date_search_pattern") or "").strip()
    file_type = (request.POST.get("date_search_file_type") or "all").strip().lower()

    if not folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder first."},
            status=400,
        )
    if not date_search_pattern:
        return JsonResponse(
            {"ok": False, "message": "Date search pattern is required."},
            status=400,
        )

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_rename_content_date_folder"] = str(root_path)
    request.session["utilities_rename_content_date_pattern"] = date_search_pattern
    request.session["utilities_rename_content_date_file_type"] = file_type
    try:
        report = rename_direct_files_by_content_date(
            root_path,
            date_search_pattern=date_search_pattern,
            file_type=file_type,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except OSError as exc:
        return JsonResponse({"ok": False, "message": f"Rename failed: {exc}"}, status=500)

    payload = {
        "ok": True,
        "renamed_count": report.renamed_count,
        "scanned_files": report.scanned_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Renamed {report.renamed_count} file(s) in '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) where pattern was not found/invalid "
            "or due to file conflicts/errors."
        )
    return JsonResponse(payload)


@login_required
@require_POST
def move_files_to_fy_folder(request):
    folder = (
        (request.POST.get("move_to_fy_folder") or "").strip()
        or request.session.get("utilities_move_to_fy_folder", "")
    )
    if not folder:
        return JsonResponse(
            {"ok": False, "message": "Select a folder first."},
            status=400,
        )

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Folder not found: {root_path}"},
            status=400,
        )

    request.session["utilities_move_to_fy_folder"] = str(root_path)
    try:
        report = move_direct_files_to_fy_folders(root_path)
    except OSError as exc:
        return JsonResponse(
            {"ok": False, "message": f"FY move failed: {exc}"},
            status=500,
        )

    payload = {
        "ok": True,
        "moved_count": report.moved_count,
        "scanned_files": report.scanned_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Moved {report.moved_count} file(s) into FY folders under '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) with invalid date prefix, "
            "conflicts, or file errors."
        )
    return JsonResponse(payload)


@login_required
@require_POST
def move_files_name_contains(request):
    search_folder = (
        (request.POST.get("move_name_search_folder") or "").strip()
        or request.session.get("utilities_move_name_search_folder", "")
    )
    target_folder = (request.POST.get("move_name_target_folder") or "").strip()
    phrase = (request.POST.get("move_name_contains_text") or "").strip()

    if not search_folder:
        return JsonResponse({"ok": False, "message": "Search folder is required."}, status=400)
    if not target_folder:
        return JsonResponse({"ok": False, "message": "Target folder is required."}, status=400)
    if not phrase:
        return JsonResponse({"ok": False, "message": "File name contains is required."}, status=400)

    src = Path(search_folder).expanduser()
    raw_tgt = Path(target_folder).expanduser()
    tgt = raw_tgt if raw_tgt.is_absolute() else (src / raw_tgt)
    if not src.exists() or not src.is_dir():
        return JsonResponse({"ok": False, "message": f"Search folder not found: {src}"}, status=400)
    if not tgt.exists():
        try:
            tgt.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return JsonResponse({"ok": False, "message": f"Cannot create target folder: {exc}"}, status=400)
    if not tgt.is_dir():
        return JsonResponse({"ok": False, "message": f"Target path is not a folder: {tgt}"}, status=400)

    request.session["utilities_move_name_search_folder"] = str(src)
    request.session["utilities_move_name_target_folder"] = str(tgt)
    try:
        report = move_direct_files_name_contains(src, tgt, phrase)
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except OSError as exc:
        return JsonResponse({"ok": False, "message": f"Move failed: {exc}"}, status=500)

    payload = {
        "ok": True,
        "moved_count": report.moved_count,
        "scanned_files": report.scanned_count,
        "matched_count": report.matched_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Moved {report.moved_count} file(s) from '{report.source_root}' to '{report.target_root}'. "
            f"Scanned {report.scanned_count} direct file(s)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) due to conflicts or file errors."
        )
    return JsonResponse(payload)


@login_required
@require_POST
def delete_duplicate_files(request):
    source_folder = (
        (request.POST.get("duplicate_source_folder") or "").strip()
        or request.session.get("utilities_duplicate_source_folder", "")
    )
    target_folder = (
        (request.POST.get("duplicate_target_folder") or "").strip()
        or request.session.get("utilities_duplicate_target_folder", "")
    )

    if not source_folder:
        return JsonResponse(
            {"ok": False, "message": "Select a source folder first."},
            status=400,
        )
    if not target_folder:
        return JsonResponse(
            {"ok": False, "message": "Select a target folder first."},
            status=400,
        )

    source_root = Path(source_folder).expanduser()
    target_root = Path(target_folder).expanduser()

    if not source_root.exists() or not source_root.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Source folder not found: {source_root}"},
            status=400,
        )
    if not target_root.exists() or not target_root.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Target folder not found: {target_root}"},
            status=400,
        )

    request.session["utilities_duplicate_source_folder"] = str(source_root)
    request.session["utilities_duplicate_target_folder"] = str(target_root)

    try:
        source_resolved = source_root.resolve()
        target_resolved = target_root.resolve()
        if source_resolved == target_resolved:
            raise ValueError("Source and target folders cannot be the same.")
        if source_resolved.is_relative_to(target_resolved) or target_resolved.is_relative_to(source_resolved):
            raise ValueError("Source and target folders cannot be nested within each other.")
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    job_id = str(uuid.uuid4())
    with _DUPLICATE_JOBS_LOCK:
        _DUPLICATE_JOBS[job_id] = {
            "done": False,
            "phase": "queued",
            "current": 0,
            "total": None,
            "progress_percent": 5,
            "message": "Job queued...",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    _start_duplicate_job(job_id=job_id, source_root=source_root, target_root=target_root)

    return JsonResponse(
        {
            "ok": True,
            "job_id": job_id,
            "message": "Duplicate cleanup started.",
        }
    )


@login_required
@require_GET
def duplicate_delete_status(request, job_id):
    with _DUPLICATE_JOBS_LOCK:
        job = _DUPLICATE_JOBS.get(job_id)

    if not job:
        return JsonResponse({"ok": False, "message": "Job not found."}, status=404)

    response_payload = {
        "ok": True,
        "job_id": job_id,
        "done": job["done"],
        "phase": job["phase"],
        "current": job["current"],
        "total": job["total"],
        "progress_percent": job["progress_percent"],
        "message": job["message"],
    }
    if job.get("error"):
        response_payload["error"] = job["error"]
    if job.get("result"):
        response_payload["result"] = job["result"]
    return JsonResponse(response_payload)


@login_required
@require_POST
def similar_files_report_start(request):
    reference_raw = (
        (request.POST.get("reference_file") or "").strip()
        or request.session.get("utilities_similar_reference_file", "")
    )
    threshold_raw = (request.POST.get("similar_threshold_pct") or "95").strip()

    if not reference_raw:
        return JsonResponse(
            {"ok": False, "message": "Select a reference file first."},
            status=400,
        )

    try:
        threshold_pct = float(threshold_raw)
    except ValueError:
        return JsonResponse(
            {"ok": False, "message": "Threshold must be a number."},
            status=400,
        )

    if threshold_pct < 1 or threshold_pct > 100:
        return JsonResponse(
            {"ok": False, "message": "Threshold must be between 1 and 100."},
            status=400,
        )

    reference_file = Path(reference_raw).expanduser()
    request.session["utilities_similar_reference_file"] = str(reference_file)

    if not reference_file.exists() or not reference_file.is_file():
        return JsonResponse(
            {"ok": False, "message": f"Reference file not found: {reference_file}"},
            status=400,
        )
    scan_folder = reference_file.resolve().parent
    if not scan_folder.exists() or not scan_folder.is_dir():
        return JsonResponse(
            {"ok": False, "message": f"Reference folder not found: {scan_folder}"},
            status=400,
        )

    job_id = str(uuid.uuid4())
    with _SIMILAR_REF_JOBS_LOCK:
        _SIMILAR_REF_JOBS[job_id] = {
            "done": False,
            "phase": "queued",
            "current": 0,
            "total": None,
            "progress_percent": 5,
            "message": "Job queued...",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    _start_similar_to_reference_job(
        job_id=job_id,
        reference_file=reference_file,
        scan_folder=scan_folder,
        threshold=threshold_pct / 100.0,
    )
    return JsonResponse(
        {"ok": True, "job_id": job_id, "message": "Similar files scan started."}
    )


@login_required
@require_GET
def similar_files_report_status(request, job_id):
    with _SIMILAR_REF_JOBS_LOCK:
        job = _SIMILAR_REF_JOBS.get(job_id)
    if not job:
        return JsonResponse({"ok": False, "message": "Job not found."}, status=404)

    payload = {
        "ok": True,
        "job_id": job_id,
        "done": job["done"],
        "phase": job["phase"],
        "current": job["current"],
        "total": job["total"],
        "progress_percent": job["progress_percent"],
        "message": job["message"],
    }
    if job.get("error"):
        payload["error"] = job["error"]
    if job.get("result"):
        payload["result"] = job["result"]
    return JsonResponse(payload)


@login_required
@require_POST
def find_similar_files(request):
    selected_folder = (
        (request.POST.get("similar_folder") or "").strip()
        or request.session.get("utilities_similar_files_folder", "")
    )
    threshold_raw = (request.POST.get("similar_threshold_pct") or "95").strip()

    if not selected_folder:
        return JsonResponse({"ok": False, "message": "Select a folder first."}, status=400)

    try:
        threshold_pct = float(threshold_raw)
    except ValueError:
        return JsonResponse({"ok": False, "message": "Threshold must be a number."}, status=400)

    if threshold_pct < 1 or threshold_pct > 100:
        return JsonResponse(
            {"ok": False, "message": "Threshold must be between 1 and 100."},
            status=400,
        )

    root = Path(selected_folder).expanduser()
    if not root.exists() or not root.is_dir():
        return JsonResponse({"ok": False, "message": f"Folder not found: {root}"}, status=400)

    request.session["utilities_similar_files_folder"] = str(root)
    threshold = threshold_pct / 100.0

    job_id = str(uuid.uuid4())
    with _SIMILAR_JOBS_LOCK:
        _SIMILAR_JOBS[job_id] = {
            "done": False,
            "phase": "queued",
            "current": 0,
            "total": None,
            "progress_percent": 5,
            "message": "Job queued...",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    _start_similar_files_job(job_id=job_id, root_folder=root, threshold=threshold)
    return JsonResponse({"ok": True, "job_id": job_id, "message": "Similar files scan started."})


@login_required
@require_GET
def similar_files_status(request, job_id):
    with _SIMILAR_JOBS_LOCK:
        job = _SIMILAR_JOBS.get(job_id)
    if not job:
        return JsonResponse({"ok": False, "message": "Job not found."}, status=404)

    payload = {
        "ok": True,
        "job_id": job_id,
        "done": job["done"],
        "phase": job["phase"],
        "current": job["current"],
        "total": job["total"],
        "progress_percent": job["progress_percent"],
        "message": job["message"],
    }
    if job.get("error"):
        payload["error"] = job["error"]
    if job.get("result"):
        payload["result"] = job["result"]
    return JsonResponse(payload)


