from config.views._std_imports import *  # noqa: F403

from .access import (
    _engagement_queryset_for_user,
    _has_module_access,
)
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS

from .utility_jobs import *  # noqa: F403
from .utility_jobs import (
    _DUPLICATE_JOBS,
    _DUPLICATE_JOBS_LOCK,
    _SIMILAR_JOBS,
    _SIMILAR_JOBS_LOCK,
    _SIMILAR_REF_JOBS,
    _SIMILAR_REF_JOBS_LOCK,
    _EXCEL_IMPORT_JOBS,
    _EXCEL_IMPORT_JOBS_LOCK,
    _MOVE_ALL_JOBS,
    _MOVE_ALL_JOBS_LOCK,
    _start_duplicate_job,
    _start_similar_files_job,
    _start_similar_to_reference_job,
    _start_excel_import_job,
    _start_move_all_files_job,
    _save_excel_import_preferences,
    _is_truthy_form_value,
    _excel_import_mapping_warning,
)

@login_required
def utilities(request):
    if not _has_module_access(request.user, MODULE_TOOLS):
        raise PermissionDenied("Admin only.")
    selected_empty_folder = request.session.get("utilities_selected_folder", "")
    duplicate_source_folder = request.session.get("utilities_duplicate_source_folder", "")
    duplicate_target_folder = request.session.get("utilities_duplicate_target_folder", "")
    content_search_folder = request.session.get("utilities_content_search_folder", "")
    move_all_source_folder = request.session.get("utilities_move_all_source_folder", "")
    move_all_target_folder = request.session.get("utilities_move_all_target_folder", "")
    prefix_fy_xml_folder = request.session.get("utilities_prefix_fy_xml_folder", "")
    return render(
        request,
        "utilities.html",
        {
            "selected_empty_folder": selected_empty_folder,
            "duplicate_source_folder": duplicate_source_folder,
            "duplicate_target_folder": duplicate_target_folder,
            "content_search_folder": content_search_folder,
            "move_all_source_folder": move_all_source_folder,
            "move_all_target_folder": move_all_target_folder,
            "prefix_fy_xml_folder": prefix_fy_xml_folder,
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
            "cleanup_fy_folder": request.session.get("utilities_cleanup_fy_folder", ""),
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
    move_first_chars_folder = request.session.get("utilities_move_first_chars_folder", "")
    return render(
        request,
        "organize_files_utilities.html",
        {
            "move_to_fy_folder": move_to_fy_folder,
            "move_name_search_folder": move_name_search_folder,
            "move_name_target_folder": move_name_target_folder,
            "move_first_chars_folder": move_first_chars_folder,
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
            payload["warning"] += f" ΓÇª +{len(report.errors) - 5} more."
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
def select_prefix_fy_xml_folder(request):
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

    request.session["utilities_prefix_fy_xml_folder"] = str(root_path)
    messages.success(request, f"Selected folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def process_it_xml_files(request):
    folder = (
        (request.POST.get("prefix_fy_xml_folder") or "").strip()
        or request.session.get("utilities_prefix_fy_xml_folder", "")
    )

    if not folder:
        return JsonResponse({"ok": False, "message": "Folder is required."}, status=400)

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse({"ok": False, "message": f"Folder not found: {root_path}"}, status=400)

    request.session["utilities_prefix_fy_xml_folder"] = str(root_path)
    try:
        report = prefix_fy_from_tax_files(root_path)
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
            f"Processed {report.renamed_count} file(s) in '{report.root}'. "
            f"Scanned {report.scanned_count} direct .xml/.json file(s) only (no subfolders)."
        ),
    }

    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) where AssessmentYear was not found "
            "or the file was already compliant."
        )
    return JsonResponse(payload)


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
def select_move_all_source_folder(request):
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

    request.session["utilities_move_all_source_folder"] = str(root_path)
    messages.success(request, f"Selected move-all-files source folder: {root_path}")
    return redirect("utilities")


@login_required
@require_POST
def select_move_all_target_folder(request):
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

    request.session["utilities_move_all_target_folder"] = str(root_path)
    messages.success(request, f"Selected move-all-files target folder: {root_path}")
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
def select_cleanup_fy_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("rename_files_utilities")

    if root_path is None:
        messages.info(request, "Clean up file names folder selection cancelled.")
        return redirect("rename_files_utilities")

    request.session["utilities_cleanup_fy_folder"] = str(root_path)
    messages.success(request, f"Selected folder for clean up file names: {root_path}")
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
def select_move_first_chars_folder(request):
    try:
        root_path = choose_root_folder()
    except RuntimeError:
        messages.error(
            request,
            "Could not open folder selector. Run this on a machine with desktop access.",
        )
        return redirect("organize_files_utilities")

    if root_path is None:
        messages.info(request, "Folder selection cancelled.")
        return redirect("organize_files_utilities")

    request.session["utilities_move_first_chars_folder"] = str(root_path)
    messages.success(request, f"Selected folder: {root_path}")
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
            payload["warning"] += f" ΓÇª and {len(report.errors) - 5} more."
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
    prefix = (request.POST.get("file_name_prefix") or "").strip()

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
            prefix=prefix,
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
def cleanup_fy_file_names(request):
    folder = (
        (request.POST.get("cleanup_fy_folder") or "").strip()
        or request.session.get("utilities_cleanup_fy_folder", "")
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

    request.session["utilities_cleanup_fy_folder"] = str(root_path)
    try:
        report = cleanup_fy_duplicate_refs(root_path)
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
            f"Cleaned up {report.renamed_count} file(s) in '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
        ),
    }
    if report.skipped_count:
        payload["warning"] = (
            f"Skipped {report.skipped_count} file(s) that don't start with FYNN "
            "or were already clean."
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


@login_required
@require_POST
def move_files_by_first_chars(request):
    folder = (
        (request.POST.get("move_first_chars_folder") or "").strip()
        or request.session.get("utilities_move_first_chars_folder", "")
    )
    char_count_raw = (request.POST.get("move_first_chars_count") or "").strip()

    if not folder:
        return JsonResponse({"ok": False, "message": "Folder is required."}, status=400)
    if not char_count_raw:
        return JsonResponse({"ok": False, "message": "Number of characters is required."}, status=400)

    try:
        char_count = int(char_count_raw)
    except ValueError:
        return JsonResponse({"ok": False, "message": "Number of characters must be a whole number."}, status=400)

    root_path = Path(folder).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return JsonResponse({"ok": False, "message": f"Folder not found: {root_path}"}, status=400)

    request.session["utilities_move_first_chars_folder"] = str(root_path)
    try:
        report = move_direct_files_by_first_chars(root_path, char_count=char_count)
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except OSError as exc:
        return JsonResponse({"ok": False, "message": f"Move failed: {exc}"}, status=500)

    payload = {
        "ok": True,
        "moved_count": report.moved_count,
        "scanned_files": report.scanned_count,
        "skipped_count": report.skipped_count,
        "message": (
            f"Moved {report.moved_count} file(s) into folders in '{report.root}'. "
            f"Scanned {report.scanned_count} direct file(s) only (no subfolders)."
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
def move_all_files(request):
    source_folder = (
        (request.POST.get("move_all_source_folder") or "").strip()
        or request.session.get("utilities_move_all_source_folder", "")
    )
    target_folder = (
        (request.POST.get("move_all_target_folder") or "").strip()
        or request.session.get("utilities_move_all_target_folder", "")
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

    request.session["utilities_move_all_source_folder"] = str(source_root)
    request.session["utilities_move_all_target_folder"] = str(target_root)

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
    with _MOVE_ALL_JOBS_LOCK:
        _MOVE_ALL_JOBS[job_id] = {
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

    _start_move_all_files_job(job_id=job_id, source_root=source_root, target_root=target_root)

    return JsonResponse(
        {
            "ok": True,
            "job_id": job_id,
            "message": "Move all files started.",
        }
    )


@login_required
@require_GET
def move_all_files_status(request, job_id):
    with _MOVE_ALL_JOBS_LOCK:
        job = _MOVE_ALL_JOBS.get(job_id)

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


