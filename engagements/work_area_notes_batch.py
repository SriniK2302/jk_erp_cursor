"""Batch save for work area notes (header amount + grid of audit queries)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import (
    AuditQuery,
    AuditQueryAttachment,
    Engagement,
    EngagementDivision,
    ServiceEngagementChecklistItem,
    ServiceEngagementChecklistWorkArea,
)


def batch_save_wants_json(request) -> bool:
    accept = request.headers.get("Accept") or ""
    if "application/json" in accept:
        return True
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def json_batch_save_response(*, ok: bool, errors: list[str] | None = None, status: int = 200):
    if not ok:
        return JsonResponse(
            {"ok": False, "errors": errors or ["Could not save this line."]},
            status=status if status != 200 else 400,
        )
    return JsonResponse({"ok": True}, status=status)


def _service_id_for_work_area(work_area) -> int | None:
    engagement = getattr(work_area, "engagement", None)
    if engagement is not None:
        return engagement.service_id
    division = getattr(work_area, "division", None)
    if division is not None:
        return division.engagement.service_id
    if getattr(work_area, "engagement_id", None):
        return (
            Engagement.objects.filter(pk=work_area.engagement_id)
            .values_list("service_id", flat=True)
            .first()
        )
    if getattr(work_area, "division_id", None):
        return (
            EngagementDivision.objects.filter(pk=work_area.division_id)
            .values_list("engagement__service_id", flat=True)
            .first()
        )
    return None


def resolve_service_checklist_template(work_area):
    """
    Checklist template for this work area: explicit FK, else same-name template
    on the engagement's service (legacy rows added without the FK).
    """
    cached = getattr(work_area, "_resolved_service_checklist_template", None)
    if cached is not None:
        return cached

    tpl_id = getattr(work_area, "service_checklist_work_area_id", None)
    if tpl_id:
        tpl = ServiceEngagementChecklistWorkArea.objects.filter(pk=tpl_id).first()
        work_area._resolved_service_checklist_template = tpl
        return tpl

    service_id = _service_id_for_work_area(work_area)
    wa_name = (getattr(work_area, "work_area_name", None) or "").strip()
    tpl = None
    if service_id and wa_name:
        name_cf = wa_name.casefold()
        for candidate in ServiceEngagementChecklistWorkArea.objects.filter(
            service_id=service_id
        ).order_by("sort_order", "id"):
            if (candidate.name or "").strip().casefold() == name_cf:
                tpl = candidate
                break

    work_area._resolved_service_checklist_template = tpl
    return tpl


def checklist_items_queryset(work_area):
    tpl = resolve_service_checklist_template(work_area)
    if tpl is None:
        return ServiceEngagementChecklistItem.objects.none()
    return ServiceEngagementChecklistItem.objects.filter(work_area_id=tpl.pk).order_by(
        "sort_order", "id"
    )


def checklist_items_payload(checklist_items):
    """JSON-serializable id + full line text for the batch-form checklist picker UI."""
    return [
        {"id": obj.pk, "text": (obj.line_text or "").strip()}
        for obj in checklist_items
    ]


def work_area_has_checklist_template(work_area) -> bool:
    return resolve_service_checklist_template(work_area) is not None


def work_area_notes_list_page_context(
    *,
    engagement,
    division=None,
    rows,
) -> dict:
    """Shared template context for engagement- and division-scoped notes list pages."""
    from django.urls import reverse

    is_division = division is not None
    if is_division:
        client_line = (
            f"{division.engagement.client.display_name} · "
            f"{division.engagement.fiscal_year.fy_no} · "
            f"{division.engagement.service.service_desc} · "
            f"{division.division_name}"
        )
        return {
            "engagement": engagement,
            "division": division,
            "is_division_scope": True,
            "rows": rows,
            "notes_list_subtitle": f"{client_line} · Division work areas only",
            "notes_list_empty_message": "No notes on division work areas yet.",
            "notes_list_grid_id": "division-work-area-notes",
            "notes_list_back_url": reverse(
                "engagement_division_work_areas", kwargs={"division_pk": division.pk}
            ),
            "notes_list_back_label": "← Back to Division Work Areas",
        }
    return {
        "engagement": engagement,
        "division": None,
        "is_division_scope": False,
        "rows": rows,
        "notes_list_subtitle": (
            f"{engagement.client.display_name} · {engagement.fiscal_year.fy_no} · "
            f"{engagement.service.service_desc} · Engagement work areas only"
        ),
        "notes_list_empty_message": "No notes on engagement work areas yet.",
        "notes_list_grid_id": "engagement-work-area-notes",
        "notes_list_back_url": reverse(
            "engagement_work_areas", kwargs={"engagement_pk": engagement.pk}
        ),
        "notes_list_back_label": "← Back to Engagement Work Areas",
    }


def work_area_notes_page_context(
    work_area,
    queries,
    *,
    engagement,
    division=None,
    engagement_work_area: bool,
):
    """Shared template context for engagement- and division-scoped work area notes."""
    from django.urls import reverse

    checklist_items = list(checklist_items_queryset(work_area))
    is_division = division is not None
    if is_division:
        notes_back_url = reverse("engagement_divisions")
        notes_back_label = "← Back to Engagement Divisions"
        notes_documents_url = reverse(
            "engagement_division_work_area_documents",
            kwargs={"division_pk": division.pk, "work_area_pk": work_area.pk},
        )
        form_post_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={"division_pk": division.pk, "work_area_pk": work_area.pk},
        )
    else:
        notes_back_url = reverse(
            "engagement_work_areas", kwargs={"engagement_pk": engagement.pk}
        )
        notes_back_label = "← Back to Engagement Work Areas"
        notes_documents_url = reverse(
            "engagement_work_area_documents",
            kwargs={"engagement_pk": engagement.pk, "work_area_pk": work_area.pk},
        )
        form_post_url = reverse(
            "engagement_work_area_queries",
            kwargs={"engagement_pk": engagement.pk, "work_area_pk": work_area.pk},
        )
    return {
        "engagement": engagement,
        "division": division,
        "is_division_scope": is_division,
        "work_area": work_area,
        "queries": queries,
        "checklist_items": checklist_items,
        "checklist_items_payload": checklist_items_payload(checklist_items),
        "work_area_has_checklist_template": work_area_has_checklist_template(work_area),
        "saved_checklist_item_ids": saved_checklist_item_ids(
            work_area, engagement_work_area=engagement_work_area
        ),
        "notes_back_url": notes_back_url,
        "notes_back_label": notes_back_label,
        "form_post_url": form_post_url,
        "notes_documents_url": notes_documents_url,
        "notes_all_documents_url": reverse(
            "engagement_uploaded_documents_report",
            kwargs={"engagement_pk": engagement.pk},
        ),
        "responder_type_choices": AuditQuery.RESPONDER_TYPE_CHOICES,
        "entry_type_choices": AuditQuery.ENTRY_TYPE_CHOICES,
        "amount_unit_choices": AuditQuery.AMOUNT_UNIT_CHOICES,
    }


def saved_checklist_item_ids(work_area, *, engagement_work_area: bool) -> list[int]:
    qs = AuditQuery.objects.filter(service_checklist_item__isnull=False)
    if engagement_work_area:
        qs = qs.filter(engagement_work_area=work_area)
    else:
        qs = qs.filter(division_work_area=work_area)
    return list(qs.values_list("service_checklist_item_id", flat=True))


def _normalize_amount_unit(raw: str) -> str:
    u = (raw or "").strip().lower()
    if u in {
        AuditQuery.AMOUNT_UNIT_LAKHS,
        AuditQuery.AMOUNT_UNIT_RS,
        AuditQuery.AMOUNT_UNIT_CRORES,
    }:
        return u
    return AuditQuery.AMOUNT_UNIT_LAKHS


def _parse_header_amount(request) -> tuple[object, str]:
    """Returns (Decimal | None | 'INVALID', unit)."""
    amt_raw = (request.POST.get("batch_wa_amount") or "").strip()
    unit = _normalize_amount_unit(request.POST.get("batch_wa_amount_unit"))
    if not amt_raw:
        return None, unit
    try:
        return Decimal(amt_raw), unit
    except (InvalidOperation, ValueError):
        return "INVALID", unit


def _resolve_checklist_item(work_area, raw_id: str):
    if not (raw_id or "").strip().isdigit():
        return None
    pk = int(raw_id)
    return checklist_items_queryset(work_area).filter(pk=pk).first()


def _row_needs_content_message() -> str:
    return (
        "Enter a checklist line, query or remarks, or attach a file."
    )


def _checklist_line_text(item, checklist_label: str) -> str:
    if item is not None:
        return (item.line_text or "").strip()
    return (checklist_label or "").strip()


def _pad_batch_lists(request) -> tuple[list, list, list, list, list, list, int]:
    dates = request.POST.getlist("batch_row_date")
    types = request.POST.getlist("batch_row_type")
    checklist_raw = request.POST.getlist("batch_row_checklist")
    checklist_labels = request.POST.getlist("batch_row_checklist_label")
    texts = request.POST.getlist("batch_row_text")
    expected_list = request.POST.getlist("batch_row_expected")
    n = max(
        len(dates),
        len(types),
        len(checklist_raw),
        len(checklist_labels),
        len(texts),
        len(expected_list),
        1,
    )
    while len(dates) < n:
        dates.append("")
    while len(types) < n:
        types.append("")
    while len(checklist_raw) < n:
        checklist_raw.append("")
    while len(checklist_labels) < n:
        checklist_labels.append("")
    while len(texts) < n:
        texts.append("")
    while len(expected_list) < n:
        expected_list.append("")
    return dates, types, checklist_raw, checklist_labels, texts, expected_list, n


def _parse_row_at_index(
    request,
    work_area,
    i: int,
    *,
    dates,
    types,
    checklist_raw,
    checklist_labels,
    texts,
    expected_list,
    allow_skip_empty: bool,
) -> tuple[dict | None, list[str]]:
    """
    Build one row payload for index i.
    If allow_skip_empty and row has no text/uploads, returns (None, []).
    Otherwise returns (row dict, []) or (None, [error, ...]).
    """
    errors: list[str] = []
    qd = parse_date((dates[i] or "").strip())
    entry_type = (types[i] or "").strip().lower()
    text = (texts[i] or "").strip()
    uploads = request.FILES.getlist(f"batch_row_files_{i}")
    raw_chk = (checklist_raw[i] or "").strip()
    checklist_label = (checklist_labels[i] or "").strip()
    item = None
    if raw_chk:
        item = _resolve_checklist_item(work_area, raw_chk)
        if item is None:
            if checklist_label:
                raw_chk = ""
            else:
                errors.append("Invalid checklist line.")
                return None, errors
        elif not checklist_label:
            checklist_label = (item.line_text or "").strip()
    has_checklist = bool(item is not None or checklist_label)
    if not text and not uploads and not has_checklist:
        if allow_skip_empty:
            return None, []
        errors.append(_row_needs_content_message())
        return None, errors
    if qd is None:
        errors.append("Enter a valid date.")
        return None, errors
    if entry_type == "status":
        entry_type = AuditQuery.ENTRY_TYPE_REMARK
    if entry_type not in {
        AuditQuery.ENTRY_TYPE_QUERY,
        AuditQuery.ENTRY_TYPE_REMARK,
    }:
        entry_type = AuditQuery.ENTRY_TYPE_QUERY
    exp = (expected_list[i] or "").strip().lower()
    if exp not in {
        AuditQuery.RESPONDER_INTERNAL,
        AuditQuery.RESPONDER_CLIENT,
    }:
        exp = AuditQuery.RESPONDER_INTERNAL
    if not text:
        if uploads:
            text = "(See attachments)"
        elif has_checklist:
            text = _checklist_line_text(item, checklist_label)
        else:
            errors.append(_row_needs_content_message())
            return None, errors
    return (
        {
            "i": i,
            "query_date": qd,
            "entry_type": entry_type,
            "item": item,
            "checklist_label": checklist_label,
            "text": text,
            "expected": exp,
            "uploads": uploads,
        },
        [],
    )


def _apply_work_area_header_amount(work_area, amount_result, amount_unit) -> None:
    if amount_result is None:
        work_area.monetary_amount = None
    else:
        work_area.monetary_amount = amount_result
    work_area.monetary_amount_unit = amount_unit
    work_area.save(
        update_fields=[
            "monetary_amount",
            "monetary_amount_unit",
            "updated_on",
        ]
    )


def _create_audit_queries_from_rows(
    request,
    work_area,
    *,
    engagement_work_area: bool,
    rows_to_save: list[dict],
) -> None:
    for row in rows_to_save:
        subject = work_area.work_area_name
        suffix = ""
        if row["item"]:
            suffix = (row["item"].line_text or "").strip()
        elif row.get("checklist_label"):
            suffix = row["checklist_label"].strip()
        if suffix:
            subject = f"{work_area.work_area_name} · {suffix}"[:255]

        et = row["entry_type"]
        is_query = et == AuditQuery.ENTRY_TYPE_QUERY
        kwargs = {
            "query_date": row["query_date"],
            "entry_type": et,
            "subject": subject,
            "amount": None,
            "amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
            "query_text": row["text"],
            "response_expected_from": (
                row["expected"] if is_query else AuditQuery.RESPONDER_INTERNAL
            ),
            "status": (
                AuditQuery.STATUS_OPEN if is_query else AuditQuery.STATUS_CLOSED
            ),
            "service_checklist_item": row["item"],
            "created_by": request.user,
        }
        if engagement_work_area:
            kwargs["engagement_work_area"] = work_area
            kwargs["division_work_area"] = None
        else:
            kwargs["engagement_work_area"] = None
            kwargs["division_work_area"] = work_area

        query = AuditQuery.objects.create(**kwargs)
        for upload in row["uploads"][:20]:
            AuditQueryAttachment.objects.create(
                query=query,
                file=upload,
                original_filename=(upload.name or "file")[:255],
                created_by=request.user,
            )


def add_all_checklist_lines_to_notes_log(
    request, work_area, *, engagement_work_area: bool
) -> tuple[int, list[str]]:
    """
    Create one open query note per checklist template line not already in the log.
    Returns (created_count, error_messages).
    """
    if not work_area_has_checklist_template(work_area):
        return 0, ["This work area has no checklist template linked."]

    items = list(checklist_items_queryset(work_area))
    if not items:
        return 0, ["The linked checklist template has no lines yet."]

    existing_ids = set(saved_checklist_item_ids(work_area, engagement_work_area=engagement_work_area))
    to_add = [item for item in items if item.pk not in existing_ids]
    if not to_add:
        return 0, []

    note_date = timezone.localdate()
    rows_to_save = []
    for item in to_add:
        line = (item.line_text or "").strip()
        if not line:
            continue
        rows_to_save.append(
            {
                "query_date": note_date,
                "entry_type": AuditQuery.ENTRY_TYPE_QUERY,
                "item": item,
                "checklist_label": line,
                "text": line,
                "expected": AuditQuery.RESPONDER_INTERNAL,
                "uploads": [],
            }
        )

    if not rows_to_save:
        return 0, ["The linked checklist template has no lines with text."]

    with transaction.atomic():
        _create_audit_queries_from_rows(
            request,
            work_area,
            engagement_work_area=engagement_work_area,
            rows_to_save=rows_to_save,
        )
    return len(rows_to_save), []


def save_work_area_notes_batch_single_row(
    request, work_area, row_index: int, *, engagement_work_area: bool
) -> list[str]:
    """
    Save exactly one batch row (by 0-based index). Updates header amount from POST.
    Returns error messages (empty on success).
    """
    errors: list[str] = []
    amount_result, amount_unit = _parse_header_amount(request)
    if amount_result == "INVALID":
        errors.append("Enter a valid work area amount, or leave it blank.")
        return errors

    dates, types, checklist_raw, checklist_labels, texts, expected_list, n = _pad_batch_lists(
        request
    )
    if row_index < 0 or row_index >= n:
        return ["Invalid line."]

    row, row_errors = _parse_row_at_index(
        request,
        work_area,
        row_index,
        dates=dates,
        types=types,
        checklist_raw=checklist_raw,
        checklist_labels=checklist_labels,
        texts=texts,
        expected_list=expected_list,
        allow_skip_empty=False,
    )
    if row_errors:
        return row_errors
    if row is None:
        return [_row_needs_content_message()]

    with transaction.atomic():
        _apply_work_area_header_amount(work_area, amount_result, amount_unit)
        _create_audit_queries_from_rows(
            request,
            work_area,
            engagement_work_area=engagement_work_area,
            rows_to_save=[row],
        )
    return []


def save_work_area_notes_batch(request, work_area, *, engagement_work_area: bool) -> list[str]:
    """
    Parse batch POST and create AuditQuery rows + update work area header amount.
    Returns a list of error messages (empty on success).
    """
    errors: list[str] = []
    amount_result, amount_unit = _parse_header_amount(request)
    if amount_result == "INVALID":
        errors.append("Enter a valid work area amount, or leave it blank.")

    dates, types, checklist_raw, checklist_labels, texts, expected_list, n = _pad_batch_lists(
        request
    )

    rows_to_save = []
    for i in range(n):
        row, row_errors = _parse_row_at_index(
            request,
            work_area,
            i,
            dates=dates,
            types=types,
            checklist_raw=checklist_raw,
            checklist_labels=checklist_labels,
            texts=texts,
            expected_list=expected_list,
            allow_skip_empty=True,
        )
        for msg in row_errors:
            errors.append(f"Row {i + 1}: {msg}")
        if row is not None:
            rows_to_save.append(row)

    if errors:
        return errors

    if amount_result == "INVALID":
        return errors

    if not rows_to_save:
        errors.append(
            "Add at least one line with a checklist line, text, a file, or a combination."
        )
        return errors

    with transaction.atomic():
        _apply_work_area_header_amount(work_area, amount_result, amount_unit)
        _create_audit_queries_from_rows(
            request,
            work_area,
            engagement_work_area=engagement_work_area,
            rows_to_save=rows_to_save,
        )

    return []
