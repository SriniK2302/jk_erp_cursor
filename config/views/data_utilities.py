from config.views._std_imports import *  # noqa: F403

from .access import (
    _engagement_queryset_for_user,
    _has_module_access,
)
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS

from .utility_jobs import *  # noqa: F403
from .utility_jobs import (
    _EXCEL_IMPORT_JOBS,
    _EXCEL_IMPORT_JOBS_LOCK,
    _start_excel_import_job,
    _save_excel_import_preferences,
    _is_truthy_form_value,
    _excel_import_mapping_warning,
)


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
def excel_import_tables_json(request):
    """List public tables in the selected PostgreSQL database (Django default connection)."""
    postgres_db = (request.GET.get("postgres_db") or "").strip()
    if not postgres_db:
        return JsonResponse({"ok": False, "message": "Select a database first."}, status=400)
    d = settings.DATABASES["default"]
    try:
        names = list_public_tables(
            host=d.get("HOST") or "127.0.0.1",
            port=int(d.get("PORT") or 5432),
            user=d.get("USER") or "postgres",
            password=d.get("PASSWORD") or "",
            dbname=postgres_db,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "tables": names})


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


def _validate_table_exists(*, postgres_db: str, table_name: str) -> str | None:
    """Return an error message if table_name is not a real table in postgres_db, else None."""
    d = settings.DATABASES["default"]
    try:
        names = list_public_tables(
            host=d.get("HOST") or "127.0.0.1",
            port=int(d.get("PORT") or 5432),
            user=d.get("USER") or "postgres",
            password=d.get("PASSWORD") or "",
            dbname=postgres_db,
        )
    except Exception as exc:
        return f"Could not verify table: {exc}"
    if table_name not in names:
        return f"Table {table_name!r} was not found in database {postgres_db!r}. Pick a table from the list."
    return None


@login_required
@require_POST
def excel_import_match_report(request):
    """Return Excel Γåö PostgreSQL column mapping and types without importing."""
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

    table_error = _validate_table_exists(postgres_db=postgres_db, table_name=table_name)
    if table_error:
        return JsonResponse({"ok": False, "message": table_error}, status=400)

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

    table_error = _validate_table_exists(postgres_db=postgres_db, table_name=table_name)
    if table_error:
        messages.error(request, table_error)
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
        extra += (
            f" Skipped columns not in the table: "
            f"{', '.join(result['columns_not_in_table'])}."
        )
    if result.get("columns_calculated_skipped"):
        extra += (
            f" Skipped database-calculated columns (filled automatically): "
            f"{', '.join(result['columns_calculated_skipped'])}."
        )
    if result.get("auto_created_accounts"):
        extra += (
            f" Auto-created new accounts in Source Accounts: "
            f"{', '.join(result['auto_created_accounts'])}."
        )
    if result.get("opening_balance_rows_skipped"):
        extra += (
            f" Skipped {result['opening_balance_rows_skipped']} opening balance "
            f"row(s) (enter these via Opening Balances instead)."
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

    table_error = _validate_table_exists(postgres_db=postgres_db, table_name=table_name)
    if table_error:
        return JsonResponse({"ok": False, "message": table_error}, status=400)

    path = Path(raw).expanduser()
    if not path.is_file():
        return JsonResponse({"ok": False, "message": "File not found."}, status=400)

    request.session["data_excel_import_path"] = str(path)

    job_id = str(uuid.uuid4())
    with _EXCEL_IMPORT_JOBS_LOCK:
        _EXCEL_IMPORT_JOBS[job_id] = {
            "done": False,
            "phase": "queued",
            "current": 0,
            "total": None,
            "progress_percent": 5,
            "message": "Starting importΓÇª",
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
    """List databases using Django ``DATABASES['default']`` (same connection as Excel ΓåÆ PostgreSQL import)."""
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


