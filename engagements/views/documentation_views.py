from engagements.views._std_imports import *  # noqa: F403

from .access import (
    _active_time_session_for_user,
    _can_manage_structure,
    _division_work_area_queryset_for_user,
    _engagement_division_queryset_for_user,
    _engagement_queryset_for_user,
    _engagement_work_area_queryset_for_user,
    _has_engagements_module_access,
    _timer_scope_dict,
)

def engagement_documentation_maps(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = request.POST.get("action")
        if action == "delete":
            documentation_map = get_object_or_404(
                EngagementDocumentationMap,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            documentation_map.delete()
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        if action == "delete_all_documentation_maps":
            qs = engagement.documentation_maps.all()
            n = qs.count()
            if n:
                with transaction.atomic():
                    qs.delete()
                messages.success(
                    request,
                    (
                        f"Removed {n} documentation mapping(s) for this engagement "
                        "(including uploaded files under each mapping)."
                    ),
                )
            else:
                messages.info(request, "No documentation mappings to remove.")
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        if action == "prefill_from_client_classification":
            classification = engagement.client.classification
            applicable_docs = (
                EngagementDocumentation.objects.filter(
                    applicable_classifications=classification
                )
                .distinct()
                .order_by("document_stage", "standard_document")
            )
            existing_ids = set(
                engagement.documentation_maps.values_list(
                    "documentation_id", flat=True
                )
            )
            today = timezone.localdate()
            new_maps = [
                EngagementDocumentationMap(
                    engagement=engagement,
                    documentation=doc,
                    documentation_date=today,
                    created_by=request.user,
                )
                for doc in applicable_docs
                if doc.id not in existing_ids
            ]
            if new_maps:
                with transaction.atomic():
                    EngagementDocumentationMap.objects.bulk_create(new_maps)
                messages.success(
                    request,
                    (
                        f"Added {len(new_maps)} documentation mapping(s) that apply to "
                        f"{classification.classification_name}. Remove any you do not need."
                    ),
                )
            else:
                messages.info(
                    request,
                    (
                        "No new mappings were added. Either every matching item is already "
                        "mapped, or no setup documentation lists this client's classification "
                        "under Applicable To."
                    ),
                )
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
        return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)

    attachment_qs = EngagementDocumentationMapAttachment.objects.order_by(
        "-document_date", "original_filename", "pk"
    )
    documentation_maps = (
        engagement.documentation_maps.select_related("documentation")
        .annotate(
            attachment_count=Count("attachments", distinct=True),
            has_setup_word_template=Exists(
                EngagementDocumentation.objects.filter(
                    pk=OuterRef("documentation_id"),
                )
                .exclude(word_template__isnull=True)
                .exclude(word_template="")
            ),
        )
        .prefetch_related(Prefetch("attachments", queryset=attachment_qs))
        .order_by(
            "documentation_date",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    return render(
        request,
        "engagements/engagement_documentation_maps.html",
        {
            "engagement": engagement,
            "documentation_maps": documentation_maps,
        },
    )


@login_required
def engagement_documentation_missing_uploads_report(request, engagement_pk):
    """Mapped engagement + division documentation with no uploaded files yet."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    missing_rows = []
    eng_maps = (
        engagement.documentation_maps.select_related("documentation")
        .annotate(_ac=Count("attachments", distinct=True))
        .filter(_ac=0)
        .order_by(
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    for m in eng_maps:
        missing_rows.append(
            {
                "scope_label": "Engagement",
                "standard_document": m.documentation.standard_document,
                "stage_display": m.documentation.get_document_stage_display(),
                "document_stage": m.documentation.document_stage,
                "list_date": m.documentation_date,
                "files_url": reverse(
                    "engagement_documentation_map_files",
                    kwargs={"engagement_pk": engagement.pk, "map_pk": m.pk},
                ),
            }
        )
    div_maps = (
        EngagementDivisionDocumentationMap.objects.filter(
            division__engagement=engagement,
        )
        .select_related("documentation", "division")
        .annotate(_ac=Count("attachments", distinct=True))
        .filter(_ac=0)
        .order_by(
            "division__division_name",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        )
    )
    for m in div_maps:
        missing_rows.append(
            {
                "scope_label": f"Division: {m.division.division_name}",
                "standard_document": m.documentation.standard_document,
                "stage_display": m.documentation.get_document_stage_display(),
                "document_stage": m.documentation.document_stage,
                "list_date": None,
                "files_url": reverse(
                    "engagement_division_documentation_map_files",
                    kwargs={"division_pk": m.division_id, "map_pk": m.pk},
                ),
            }
        )
    missing_rows.sort(
        key=lambda r: (
            r["document_stage"],
            (r["standard_document"] or "").casefold(),
            r["scope_label"],
        )
    )
    return render(
        request,
        "engagements/engagement_documentation_missing_uploads_report.html",
        {
            "engagement": engagement,
            "missing_rows": missing_rows,
        },
    )


def _handle_engagement_duplicate_document_delete(request, engagement) -> bool:
    """Shared delete_duplicate POST handler. Returns True if the POST was handled."""
    if request.method != "POST" or request.POST.get("action") != "delete_duplicate":
        return False
    assert_engagement_open_for_management(request.user, engagement)
    source_kind = (request.POST.get("source_kind") or "").strip()
    pk_raw = (request.POST.get("pk") or "").strip()
    if not pk_raw.isdigit():
        messages.error(request, "Invalid duplicate selection.")
        return True
    row_id = int(pk_raw)
    deleted = False
    if source_kind == "engagement_attachment":
        deleted, _ = EngagementDocumentationMapAttachment.objects.filter(
            pk=row_id,
            documentation_map__engagement=engagement,
        ).delete()
    elif source_kind == "division_attachment":
        deleted, _ = EngagementDivisionDocumentationMapAttachment.objects.filter(
            pk=row_id,
            documentation_map__division__engagement=engagement,
        ).delete()
    elif source_kind == "engagement_work_area_doc":
        deleted, _ = EngagementWorkAreaDocument.objects.filter(
            pk=row_id,
            work_area__engagement=engagement,
        ).delete()
    elif source_kind == "division_work_area_doc":
        deleted, _ = DivisionWorkAreaDocument.objects.filter(
            pk=row_id,
            work_area__division__engagement=engagement,
        ).delete()
    elif source_kind == "audit_query_engagement_attachment":
        deleted, _ = AuditQueryAttachment.objects.filter(
            pk=row_id,
            query__engagement_work_area__engagement=engagement,
        ).delete()
    elif source_kind == "audit_query_division_attachment":
        deleted, _ = AuditQueryAttachment.objects.filter(
            pk=row_id,
            query__division_work_area__division__engagement=engagement,
        ).delete()
    if deleted:
        messages.success(request, "Duplicate file removed.")
    else:
        messages.error(request, "Unable to remove the selected duplicate.")
    return True


def _engagement_uploaded_document_rows(engagement):
    rows = []
    engagement_attachments = EngagementDocumentationMapAttachment.objects.select_related(
        "documentation_map__documentation"
    ).filter(documentation_map__engagement=engagement)
    for att in engagement_attachments:
        doc = att.documentation_map.documentation
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_level": "Engagement",
                "source_name": "Engagement documentation",
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_documentation_attachment_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "engagement_attachment",
                "pk": att.pk,
                "division_scope": "engagement",
                "reference_no": "",
                "remarks": "",
            }
        )

    division_attachments = (
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division", "documentation_map__documentation"
        )
        .filter(documentation_map__division__engagement=engagement)
        .all()
    )
    for att in division_attachments:
        doc = att.documentation_map.documentation
        division = att.documentation_map.division
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_level": "Division",
                "source_name": division.division_name,
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_documentation_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "division_attachment",
                "pk": att.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": "",
                "remarks": "",
            }
        )

    engagement_work_area_docs = EngagementWorkAreaDocument.objects.select_related(
        "work_area"
    ).filter(work_area__engagement=engagement)
    for doc in engagement_work_area_docs:
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_level": "Eng. work area",
                "source_name": doc.work_area.work_area_name,
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_work_area_document_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "engagement_work_area_doc",
                "pk": doc.pk,
                "division_scope": "engagement",
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    division_work_area_docs = DivisionWorkAreaDocument.objects.select_related(
        "work_area__division"
    ).filter(work_area__division__engagement=engagement)
    for doc in division_work_area_docs:
        division = doc.work_area.division
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_level": "Div. work area",
                "source_name": f"{division.division_name} / {doc.work_area.work_area_name}",
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_division_work_area_document_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "division_work_area_doc",
                "pk": doc.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    audit_eng_attachments = (
        AuditQueryAttachment.objects.select_related(
            "query__engagement_work_area",
        )
        .filter(query__engagement_work_area__engagement=engagement)
        .order_by("-created_on", "pk")
    )
    for att in audit_eng_attachments:
        wa = att.query.engagement_work_area
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_level": "Eng. WA query",
                "source_name": wa.work_area_name,
                "document_label": (att.query.subject or "").strip() or "Query note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_query_attachment_download",
                    kwargs={
                        "engagement_pk": engagement.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_engagement_attachment",
                "pk": att.pk,
                "division_scope": "engagement",
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    audit_div_attachments = (
        AuditQueryAttachment.objects.select_related(
            "query__division_work_area__division",
        )
        .filter(query__division_work_area__division__engagement=engagement)
        .order_by("-created_on", "pk")
    )
    for att in audit_div_attachments:
        wa = att.query.division_work_area
        division = wa.division
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_level": "Div. WA query",
                "source_name": f"{division.division_name} / {wa.work_area_name}",
                "document_label": (att.query.subject or "").strip() or "Query note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_query_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_division_attachment",
                "pk": att.pk,
                "division_scope": f"division:{division.pk}",
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    duplicate_groups = defaultdict(int)
    for row in rows:
        duplicate_groups[
            (
                row.get("division_scope"),
                (row.get("file_name") or "").strip().casefold(),
            )
        ] += 1
    for row in rows:
        key = (
            row.get("division_scope"),
            (row.get("file_name") or "").strip().casefold(),
        )
        row["duplicate_count"] = duplicate_groups[key]
        row["is_duplicate"] = duplicate_groups[key] > 1

    rows.sort(
        key=lambda item: (
            item["document_date"] or timezone.localdate(),
            item["created_on"] or timezone.now(),
            item["file_name"],
        ),
        reverse=True,
    )
    return rows


@login_required
def engagement_uploaded_documents_report(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if _handle_engagement_duplicate_document_delete(request, engagement):
        return redirect(
            "engagement_uploaded_documents_report", engagement_pk=engagement.pk
        )
    return render(
        request,
        "engagements/engagement_uploaded_documents_report.html",
        {
            "engagement": engagement,
            "rows": _engagement_uploaded_document_rows(engagement),
        },
    )


@login_required
def engagement_documents_and_notes(request, engagement_pk):
    """Combined report: work area notes plus every uploaded document for one engagement."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    if _handle_engagement_duplicate_document_delete(request, engagement):
        return redirect("engagement_documents_and_notes", engagement_pk=engagement.pk)
    note_rows = (
        AuditQuery.objects.filter(
            Q(engagement_work_area__engagement=engagement)
            | Q(division_work_area__division__engagement=engagement)
        )
        .select_related(
            "engagement_work_area",
            "division_work_area__division",
        )
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    return render(
        request,
        "engagements/engagement_documents_and_notes.html",
        {
            "engagement": engagement,
            "note_rows": note_rows,
            "document_rows": _engagement_uploaded_document_rows(engagement),
        },
    )


@login_required
def engagement_division_uploaded_documents_report(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    rows = []
    if request.method == "POST" and request.POST.get("action") == "delete_duplicate":
        assert_division_open_for_management(request.user, division)
        source_kind = (request.POST.get("source_kind") or "").strip()
        pk_raw = (request.POST.get("pk") or "").strip()
        if not pk_raw.isdigit():
            messages.error(request, "Invalid duplicate selection.")
            return redirect(
                "engagement_division_uploaded_documents_report",
                division_pk=division.pk,
            )
        row_id = int(pk_raw)
        deleted = False
        if source_kind == "division_attachment":
            deleted, _ = EngagementDivisionDocumentationMapAttachment.objects.filter(
                pk=row_id,
                documentation_map__division=division,
            ).delete()
        elif source_kind == "division_work_area_doc":
            deleted, _ = DivisionWorkAreaDocument.objects.filter(
                pk=row_id,
                work_area__division=division,
            ).delete()
        if deleted:
            messages.success(request, "Duplicate file removed.")
        else:
            messages.error(request, "Unable to remove the selected duplicate.")
        return redirect(
            "engagement_division_uploaded_documents_report",
            division_pk=division.pk,
        )

    division_attachments = (
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__documentation"
        )
        .filter(documentation_map__division=division)
        .all()
    )
    for att in division_attachments:
        doc = att.documentation_map.documentation
        rows.append(
            {
                "document_date": att.document_date,
                "created_on": att.created_on,
                "source_name": "Division documentation",
                "document_label": doc.standard_document,
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_documentation_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "map_pk": att.documentation_map_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "division_attachment",
                "pk": att.pk,
                "reference_no": "",
                "remarks": "",
            }
        )

    division_work_area_docs = DivisionWorkAreaDocument.objects.select_related(
        "work_area"
    ).filter(work_area__division=division)
    for doc in division_work_area_docs:
        rows.append(
            {
                "document_date": doc.document_date,
                "created_on": doc.created_on,
                "source_name": f"Work area: {doc.work_area.work_area_name}",
                "document_label": doc.description,
                "file_name": doc.original_filename,
                "download_url": reverse(
                    "engagement_division_work_area_document_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": doc.work_area_id,
                        "pk": doc.pk,
                    },
                ),
                "source_kind": "division_work_area_doc",
                "pk": doc.pk,
                "reference_no": (doc.document_reference_no or "").strip(),
                "remarks": (doc.remarks or "").strip(),
            }
        )

    note_attachments = (
        AuditQueryAttachment.objects.select_related("query__division_work_area")
        .filter(query__division_work_area__division=division)
        .order_by("-created_on", "pk")
    )
    for att in note_attachments:
        wa = att.query.division_work_area
        rows.append(
            {
                "document_date": att.query.query_date,
                "created_on": att.created_on,
                "source_name": f"Work area note: {wa.work_area_name}",
                "document_label": (att.query.subject or "").strip() or "Work area note",
                "file_name": att.original_filename,
                "download_url": reverse(
                    "engagement_division_query_attachment_download",
                    kwargs={
                        "division_pk": division.pk,
                        "work_area_pk": wa.pk,
                        "query_pk": att.query_id,
                        "pk": att.pk,
                    },
                ),
                "source_kind": "audit_query_division_attachment",
                "pk": att.pk,
                "reference_no": (att.document_reference_no or "").strip(),
                "remarks": "",
            }
        )

    duplicate_groups = defaultdict(int)
    for row in rows:
        duplicate_groups[(row.get("file_name") or "").strip().casefold()] += 1
    for row in rows:
        key = (row.get("file_name") or "").strip().casefold()
        row["duplicate_count"] = duplicate_groups[key]
        row["is_duplicate"] = duplicate_groups[key] > 1

    rows.sort(
        key=lambda item: (
            item["document_date"] or timezone.localdate(),
            item["created_on"] or timezone.now(),
            item["file_name"],
        ),
        reverse=True,
    )
    return render(
        request,
        "engagements/engagement_division_uploaded_documents_report.html",
        {
            "division": division,
            "rows": rows,
        },
    )


@login_required
def engagement_documentation_map_files(request, engagement_pk, map_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        engagement=engagement,
    )
    files_redirect = redirect(
        "engagement_documentation_map_files",
        engagement_pk=engagement.pk,
        map_pk=documentation_map.pk,
    )

    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = request.POST.get("action")
        if action == "upload_attachment":
            files = request.FILES.getlist("files")
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            description = (request.POST.get("description") or "").strip()
            if doc_date is None:
                doc_date = documentation_map.documentation_date
            if not files:
                messages.warning(request, "No files were selected.")
            else:
                n = 0
                with transaction.atomic():
                    for upload in files[:30]:
                        EngagementDocumentationMapAttachment.objects.create(
                            documentation_map=documentation_map,
                            file=upload,
                            original_filename=(upload.name or "file")[:255],
                            document_date=doc_date,
                            description=description,
                            created_by=request.user,
                        )
                        n += 1
                messages.success(request, f"Added {n} file(s).")
            return files_redirect
        if action == "delete_attachment":
            attachment = get_object_or_404(
                EngagementDocumentationMapAttachment,
                pk=request.POST.get("pk"),
                documentation_map=documentation_map,
            )
            attachment.delete()
            messages.success(request, "Attachment removed.")
            return files_redirect
        return files_redirect

    attachments = documentation_map.attachments.order_by(
        "-document_date", "original_filename", "pk"
    )
    return render(
        request,
        "engagements/engagement_documentation_map_files.html",
        {
            "engagement": engagement,
            "documentation_map": documentation_map,
            "attachments": attachments,
        },
    )


@login_required
@require_GET
def engagement_documentation_map_word_filled_download(
    request, engagement_pk, map_pk
):
    """Download the setup Word template with ``{{TOKEN}}`` placeholders filled for this engagement."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client",
            "fiscal_year",
            "service",
            "client__classification",
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        engagement=engagement,
    )
    doc_item = documentation_map.documentation
    raw_name = (getattr(doc_item.word_template, "name", None) or "").strip()
    if not raw_name:
        return HttpResponseBadRequest(
            "Fill Word needs a Word template on this standard document in "
            "Setup → Documentation. Open that row, upload a .docx template, save, "
            "then refresh this engagement page and try again."
        )
    if not raw_name.lower().endswith(".docx"):
        return HttpResponseBadRequest(
            "Only .docx templates can be auto-filled. Replace the template in "
            "Setup → Documentation with a .docx file, then try Fill Word again."
        )
    try:
        fh = doc_item.word_template.open("rb")
    except OSError:
        return HttpResponseBadRequest(
            "The database still points to a Word template, but the file is not on this "
            "server under media/ (for example after the media folder was cleared, the app "
            "was run from a different copy of the project, or the template was never "
            "uploaded in Setup only saved on your PC). Re-upload the .docx in "
            "Setup → Documentation for this standard document."
        )
    try:
        with fh:
            filled = fill_docx_template(
                fh,
                merge_context_for_engagement(
                    engagement, documentation_map=documentation_map
                ),
            )
    except Exception:
        logging.getLogger(__name__).exception(
            "Fill Word failed for engagement_pk=%s map_pk=%s documentation_pk=%s",
            engagement_pk,
            map_pk,
            doc_item.pk,
        )
        return HttpResponseServerError(
            "Fill Word failed while building the document. If this persists, "
            "check server logs or simplify placeholders in the .docx template."
        )
    unresolved = list_unresolved_tokens_in_document_xml(filled)
    if unresolved:
        logging.getLogger(__name__).warning(
            "Filled docx still contains placeholders (split runs or unknown tokens): %s",
            ", ".join(unresolved),
        )
    download_name = filled_engagement_documentation_docx_filename(
        documentation_date=documentation_map.documentation_date,
        fy_no=engagement.fiscal_year.fy_no,
        client_code=engagement.client.client_code,
        service_code=engagement.service.service_code,
        standard_document=doc_item.standard_document,
        filled_download_label=getattr(doc_item, "filled_download_label", "") or "",
    )
    response = FileResponse(
        io.BytesIO(filled),
        as_attachment=True,
        filename=download_name,
        content_type=word_template_content_type(download_name),
    )
    return response


@login_required
@require_GET
def engagement_documentation_attachment_download(
    request, engagement_pk, map_pk, pk
):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    attachment = get_object_or_404(
        EngagementDocumentationMapAttachment.objects.select_related(
            "documentation_map__engagement"
        ),
        pk=pk,
        documentation_map_id=map_pk,
        documentation_map__engagement_id=engagement.pk,
    )
    if not attachment.file:
        raise Http404
    safe_name = get_valid_filename(attachment.original_filename) or "download"
    try:
        file_handle = attachment.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


def _documentation_option_label(item):
    names = ", ".join(
        c.classification_name
        for c in sorted(
            item.applicable_classifications.all(),
            key=lambda c: c.classification_name,
        )
    )
    return f"{item.standard_document} ({item.get_document_stage_display()} - {names})"


@login_required
@require_GET
def engagement_documentation_option_search(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    q = (request.GET.get("q") or "").strip()
    current_id = (request.GET.get("for_user") or "").strip()

    used_ids = EngagementDocumentationMap.objects.filter(
        engagement=engagement
    ).values_list("documentation_id", flat=True)
    if current_id.isdigit():
        used_ids = used_ids.exclude(documentation_id=int(current_id))

    include_pk = int(current_id) if current_id.isdigit() else None
    items = (
        EngagementDocumentation.objects.prefetch_related("applicable_classifications")
        .exclude(pk__in=used_ids)
        .order_by("document_stage", "standard_document")
    )
    items = filter_engagement_documentation_by_client_classification(
        items,
        engagement.client,
        include_documentation_pk=include_pk,
    )
    if q:
        items = items.filter(
            Q(standard_document__icontains=q)
            | Q(document_stage__icontains=q)
            | Q(applicable_classifications__classification_name__icontains=q)
        ).distinct()

    payload = [{"id": item.pk, "label": _documentation_option_label(item)} for item in items[:50]]
    return JsonResponse(payload, safe=False)


def _engagement_documentation_map_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        form = EngagementDocumentationMapForm(
            request.POST,
            instance=instance,
            engagement=engagement,
        )
        if form.is_valid():
            selected_docs = form.cleaned_data.get("documentation")
            if instance is None and hasattr(selected_docs, "__iter__") and not isinstance(selected_docs, EngagementDocumentation):
                existing_ids = set(
                    EngagementDocumentationMap.objects.filter(
                        engagement=engagement
                    ).values_list("documentation_id", flat=True)
                )
                doc_date = form.cleaned_data["documentation_date"]
                new_maps = [
                    EngagementDocumentationMap(
                        engagement=engagement,
                        documentation=doc,
                        documentation_date=doc_date,
                        created_by=request.user,
                    )
                    for doc in selected_docs
                    if doc.pk not in existing_ids
                ]
                if new_maps:
                    with transaction.atomic():
                        EngagementDocumentationMap.objects.bulk_create(new_maps)
            else:
                with transaction.atomic():
                    documentation_map = form.save(commit=False)
                    if instance is None:
                        documentation_map.engagement = engagement
                        documentation_map.created_by = request.user
                    documentation_map.save()
                    if is_mr02_documentation(documentation_map.documentation):
                        documentation_map.representation_point_matrix = (
                            parse_representation_matrix_post(request.POST)
                        )
                    else:
                        documentation_map.representation_point_matrix = {}
                    documentation_map.save(
                        update_fields=["representation_point_matrix"]
                    )
            return redirect("engagement_documentation_maps", engagement_pk=engagement.pk)
    else:
        form = EngagementDocumentationMapForm(instance=instance, engagement=engagement)

    ctx = {
        "form": form,
        "engagement": engagement,
        "documentation_map": instance,
    }
    if instance is not None and instance.documentation_id:
        doc = instance.documentation
        if is_mr02_documentation(doc):
            matrix = instance.representation_point_matrix or {}
            ctx["mr02_status_choices"] = REPRESENTATION_POINT_STATUS_CHOICES
            ctx["mr02_point_rows_ui"] = [
                {
                    "p": p,
                    "status": (matrix.get(p["id"]) or {}).get("status", ""),
                    "notes": (matrix.get(p["id"]) or {}).get("notes", ""),
                }
                for p in mr02_point_rows()
            ]

    return render(
        request,
        "engagements/engagement_documentation_map_form.html",
        ctx,
    )


@login_required
def engagement_documentation_map_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    return _engagement_documentation_map_form_view(request, engagement=engagement)


@login_required
def engagement_documentation_map_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "client__classification"
        ),
        pk=engagement_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDocumentationMap.objects.select_related("documentation"),
        pk=pk,
        engagement=engagement,
    )
    return _engagement_documentation_map_form_view(
        request,
        engagement=engagement,
        instance=documentation_map,
    )
