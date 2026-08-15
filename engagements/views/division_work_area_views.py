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

from .work_area_bulk_helpers import (
    _add_division_work_areas_from_service_templates,
    _bulk_add_all_standard_work_areas,
    _bulk_delete_work_areas_without_queries,
    _division_service_work_area_pick_rows,
    _json_bulk_work_areas_response,
    _mappable_template_ids_not_on_scope,
    _resequence_scoped_work_areas,
    _service_checklist_templates_for_service,
)
from .engagement_work_area_views import (
    _apply_edit_query_post,
    _ensure_engagement_schedule_from_work_area_plan,
)
from .constants import _WORK_AREA_STATUS_FILTERS

def engagement_division_work_areas(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    eligible_source_divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .exclude(pk=division.pk)
        .filter(
            engagement__client_id=division.engagement.client_id,
            engagement__service_id=division.engagement.service_id,
            engagement__fiscal_year_id=division.engagement.fiscal_year_id,
        )
    )
    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    assert_division_open_for_management(request.user, division)

    def _division_work_areas_redirect():
        base = reverse(
            "engagement_division_work_areas", kwargs={"division_pk": division.pk}
        )
        if raw_status == "all":
            return redirect(f"{base}?{urlencode({'status': raw_status})}")
        return redirect(base)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            work_area = get_object_or_404(
                DivisionWorkArea,
                pk=request.POST.get("pk"),
                division=division,
            )
            work_area.delete()
            return _division_work_areas_redirect()
        if action == "add_from_service_templates":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            raw_ids = []
            for raw in request.POST.getlist("service_work_area_ids"):
                try:
                    raw_ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
            raw_ids = list(dict.fromkeys(raw_ids))
            created = _add_division_work_areas_from_service_templates(
                request, division, raw_ids
            )
            if created:
                messages.success(
                    request,
                    f"Added {created} work area(s) from the service standard list.",
                )
            else:
                messages.info(
                    request,
                    "No new work areas were added (none selected, or all were already present).",
                )
            return _division_work_areas_redirect()
        if action == "copy_from_division":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            source_division_id = (request.POST.get("source_division_id") or "").strip()
            if not source_division_id:
                messages.error(request, "Select a source division.")
                return _division_work_areas_redirect()
            source_division = eligible_source_divisions.filter(pk=source_division_id).first()
            if source_division is None:
                messages.error(
                    request,
                    "Selected source division is invalid. Choose one with the same client, service, and fiscal year.",
                )
                return _division_work_areas_redirect()

            with transaction.atomic():
                existing_names = {
                    name.strip().casefold()
                    for name in DivisionWorkArea.objects.filter(division=division).values_list(
                        "work_area_name", flat=True
                    )
                }
                source_work_areas = source_division.work_areas.order_by("sort_order", "id")
                created_count = 0
                for source_work_area in source_work_areas:
                    normalized = (source_work_area.work_area_name or "").strip().casefold()
                    if not normalized or normalized in existing_names:
                        continue
                    DivisionWorkArea.objects.create(
                        division=division,
                        work_area_name=source_work_area.work_area_name,
                        sort_order=9999,
                        created_by=request.user,
                    )
                    existing_names.add(normalized)
                    created_count += 1

                if created_count:
                    ordered_ids = list(
                        DivisionWorkArea.objects.filter(division=division)
                        .order_by("sort_order", "id")
                        .values_list("pk", flat=True)
                    )
                    for idx, pk in enumerate(ordered_ids, start=1):
                        DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)
            if created_count:
                messages.success(
                    request,
                    f"Copied {created_count} work area(s) from {source_division.division_name}.",
                )
            else:
                messages.info(
                    request,
                    "No new work areas to copy from the selected division.",
                )
            return _division_work_areas_redirect()
        if action == "send_confirmation_mail":
            team_mail.manual_notify_division_work_area_confirmation_mail(
                request, division
            )
            return _division_work_areas_redirect()
        if action == "send_confirmation_mail_repeat":
            team_mail.manual_notify_division_work_area_confirmation_mail_repeat(
                request, division
            )
            return _division_work_areas_redirect()
        if action == "bulk_add_all_standard":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            service_template_list = list(
                _service_checklist_templates_for_service(division.engagement.service_id)
            )
            all_service_pick_rows = _division_service_work_area_pick_rows(
                division, service_template_list
            )
            stats = _bulk_add_all_standard_work_areas(
                request,
                division=division,
                pick_rows=all_service_pick_rows,
            )
            msg = (
                f"Added {stats['work_areas_added']} work area(s) and "
                f"{stats['checklist_lines_added']} checklist line(s) to the notes log."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _division_work_areas_redirect()
        if action == "bulk_delete_all_without_queries":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            stats = _bulk_delete_work_areas_without_queries(division=division)
            msg = (
                f"Deleted {stats['deleted']} work area(s). "
                f"Kept {stats['skipped_with_queries']} with notes/queries."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _division_work_areas_redirect()
        return _division_work_areas_redirect()

    work_areas = (
        _division_work_area_queryset_for_user(request.user)
        .filter(division=division)
        .annotate(
            schedule_row_count=Count("schedule_rows"),
            document_count=Count("documents"),
            assignment_count=Count("team_assignments"),
            status_remark_count=Count("status_remarks"),
        )
        .order_by("work_area_name", "sort_order", "id")
    )
    if raw_status == "active":
        work_areas = work_areas.exclude(status=STATUS_COMPLETED)
    source_divisions = eligible_source_divisions.order_by(
        "engagement__client__client_name",
        "-engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "division_name",
    )
    service_template_list = list(
        _service_checklist_templates_for_service(division.engagement.service_id)
    )
    all_service_pick_rows = _division_service_work_area_pick_rows(
        division, service_template_list
    )
    service_work_area_pick_rows = [
        r for r in all_service_pick_rows if not r["already_added"]
    ]
    service_standard_template_count = len(service_template_list)
    return render(
        request,
        "engagements/engagement_division_work_areas.html",
        {
            "division": division,
            "work_areas": work_areas,
            "source_divisions": source_divisions,
            "work_area_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
            "service_work_area_pick_rows": service_work_area_pick_rows,
            "service_standard_template_count": service_standard_template_count,
        },
    )


@login_required
def engagement_division_work_area_notes_list(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    rows = (
        AuditQuery.objects.filter(division_work_area__division=division)
        .select_related("division_work_area")
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    ctx = work_area_notes_list_page_context(
        engagement=division.engagement,
        division=division,
        rows=rows,
    )
    return render(request, "engagements/work_area_notes_list.html", ctx)


@login_required
def engagement_division_work_area_assignments(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            assignment = get_object_or_404(
                DivisionWorkAreaTeamAssignment,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            assignment.delete()
            return redirect(
                "engagement_division_work_area_assignments",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_division_work_area_assignments",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    assignments = work_area.team_assignments.select_related("team_member")
    return render(
        request,
        "engagements/engagement_division_work_area_assignments.html",
        {
            "division": division,
            "work_area": work_area,
            "assignments": assignments,
        },
    )


def _engagement_division_work_area_assignment_form_view(
    request, division, work_area, instance=None
):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = DivisionWorkAreaTeamAssignmentForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.work_area = work_area
                assignment.created_by = request.user
            assignment.save()
            return redirect(
                "engagement_division_work_area_assignments",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = DivisionWorkAreaTeamAssignmentForm(
            instance=instance, work_area=work_area
        )
    return render(
        request,
        "engagements/engagement_division_work_area_assignment_form.html",
        {
            "form": form,
            "division": division,
            "work_area": work_area,
            "assignment": instance,
        },
    )


@login_required
def engagement_division_work_area_assignment_create(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    return _engagement_division_work_area_assignment_form_view(
        request, division=division, work_area=work_area
    )


@login_required
def engagement_division_work_area_assignment_edit(
    request, division_pk, work_area_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    work_area = get_object_or_404(
        _division_work_area_queryset_for_user(request.user),
        pk=work_area_pk,
        division=division,
    )
    assignment = get_object_or_404(
        DivisionWorkAreaTeamAssignment,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_division_work_area_assignment_form_view(
        request,
        division=division,
        work_area=work_area,
        instance=assignment,
    )


@login_required
def engagement_division_work_area_documents(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    files_redirect = redirect(
        "engagement_division_work_area_documents",
        division_pk=division.pk,
        work_area_pk=work_area.pk,
    )
    doc_options = EngagementDocumentation.objects.order_by(
        "standard_document", "document_stage"
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "edit_document":
            doc = get_object_or_404(
                DivisionWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            documentation_id = (request.POST.get("documentation_id") or "").strip()
            if doc_date is None:
                messages.error(request, "Document date is required.")
                return files_redirect
            if documentation_id:
                documentation = EngagementDocumentation.objects.filter(
                    pk=documentation_id
                ).first()
                if documentation is None:
                    messages.error(request, "Selected documentation is invalid.")
                    return files_redirect
                doc.description = documentation.standard_document
            doc.document_date = doc_date
            doc.document_reference_no = (
                request.POST.get("document_reference_no") or ""
            ).strip()[:100]
            doc.remarks = (request.POST.get("remarks") or "").strip()
            doc.save()
            messages.success(request, "Document details updated.")
            return files_redirect
        if action == "delete_document":
            doc = get_object_or_404(
                DivisionWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc.delete()
            messages.success(request, "Document removed.")
            return files_redirect
        return files_redirect

    documents = work_area.documents.order_by("-document_date", "original_filename", "pk")
    note_attachments = (
        AuditQueryAttachment.objects.filter(query__division_work_area=work_area)
        .select_related("query", "created_by")
        .order_by("-created_on", "pk")
    )
    return render(
        request,
        "engagements/engagement_division_work_area_documents.html",
        {
            "division": division,
            "work_area": work_area,
            "documents": documents,
            "note_attachments": note_attachments,
            "doc_options": doc_options,
        },
    )


@login_required
def engagement_division_work_area_queries(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea.objects.select_related(
            "division__engagement__service",
            "service_checklist_work_area",
        ),
        pk=work_area_pk,
        division=division,
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = (request.POST.get("action") or "").strip()
        if action == "add_query_batch":
            errs = save_work_area_notes_batch(
                request, work_area, engagement_work_area=False
            )
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Notes saved.")
        elif action == "add_all_checklist_lines":
            created, errs = add_all_checklist_lines_to_notes_log(
                request, work_area, engagement_work_area=False
            )
            for msg in errs:
                messages.error(request, msg)
            if created:
                messages.success(
                    request,
                    f"Added {created} checklist line(s) to the notes log.",
                )
            elif not errs:
                messages.info(request, "All checklist lines are already in the notes log.")
        elif action == "save_query_batch_row":
            try:
                row_index = int((request.POST.get("batch_row_save_index") or "").strip())
            except ValueError:
                row_index = -1
            errs = save_work_area_notes_batch_single_row(
                request, work_area, row_index, engagement_work_area=False
            )
            if batch_save_wants_json(request):
                return json_batch_save_response(ok=not errs, errors=errs)
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Line saved.")
            return redirect(
                "engagement_division_work_area_queries",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        elif action == "add_response":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            response_date = parse_date((request.POST.get("response_date") or "").strip())
            responder_type = (request.POST.get("responder_type") or "").strip().lower()
            response_text = (request.POST.get("response_text") or "").strip()
            close_query = (request.POST.get("close_query") or "").strip() == "1"
            if responder_type not in {
                AuditQuery.RESPONDER_INTERNAL,
                AuditQuery.RESPONDER_CLIENT,
            }:
                responder_type = AuditQuery.RESPONDER_INTERNAL
            if response_date is None:
                messages.error(request, "Enter a valid response date.")
            elif not response_text:
                messages.error(request, "Response text cannot be blank.")
            else:
                with transaction.atomic():
                    AuditQueryResponse.objects.create(
                        query=query,
                        response_date=response_date,
                        responder_type=responder_type,
                        response_text=response_text,
                        created_by=request.user,
                    )
                    if close_query:
                        query.status = AuditQuery.STATUS_CLOSED
                        query.save(update_fields=["status", "updated_on"])
                messages.success(request, "Response added.")
        elif action == "add_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            upload = request.FILES.get("attachment_file")
            if upload is None:
                messages.error(request, "Select a file to upload.")
            else:
                AuditQueryAttachment.objects.create(
                    query=query,
                    file=upload,
                    original_filename=(upload.name or "file")[:255],
                    document_reference_no=(
                        request.POST.get("document_reference_no") or ""
                    ).strip()[:100],
                    created_by=request.user,
                )
                messages.success(request, "Document added to query.")
        elif action == "delete_query_attachment":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            attachment = get_object_or_404(
                AuditQueryAttachment,
                pk=request.POST.get("attachment_pk"),
                query=query,
            )
            attachment.delete()
            messages.success(request, "Document deleted.")

        elif action == "edit_query":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            _apply_edit_query_post(request, query)
        elif action == "delete_query":
            query_pk = (request.POST.get("query_pk") or "").strip()
            if not query_pk:
                messages.error(request, "Select a previous query to delete.")
            else:
                query = get_object_or_404(
                    AuditQuery, pk=query_pk, division_work_area=work_area
                )
                query.delete()
                messages.success(request, "Note deleted.")
        elif action == "convert_to_working_paper":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), division_work_area=work_area
            )
            if query.entry_type != AuditQuery.ENTRY_TYPE_QUERY:
                messages.info(request, "Only query entries can be converted.")
            elif not query.converted_to_working_paper:
                query.converted_to_working_paper = True
                query.working_paper_no = f"AWP-Q{query.pk:06d}"
                query.converted_on = timezone.now()
                query.save(
                    update_fields=[
                        "converted_to_working_paper",
                        "working_paper_no",
                        "converted_on",
                        "updated_on",
                    ]
                )
                messages.success(
                    request,
                    f"Converted to working paper: {query.working_paper_no}",
                )
            else:
                messages.info(
                    request,
                    f"Already converted as {query.working_paper_no}.",
                )
        return redirect(
            "engagement_division_work_area_queries",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    queries = list(
        work_area.audit_queries.select_related(
            "created_by", "service_checklist_item"
        )
        .prefetch_related("responses__created_by", "work_documents__created_by")
        .all()
    )
    ctx = work_area_notes_page_context(
        work_area,
        queries,
        engagement=division.engagement,
        division=division,
        engagement_work_area=False,
    )

    ctx["default_date"] = timezone.localdate()
    return render(request, "engagements/work_area_queries.html", ctx)


@login_required
@require_GET
def engagement_division_work_area_document_download(
    request, division_pk, work_area_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    doc = get_object_or_404(
        DivisionWorkAreaDocument.objects.select_related("work_area__division"),
        pk=pk,
        work_area_id=work_area_pk,
        work_area__division_id=division.pk,
    )
    if not doc.file:
        raise Http404
    safe_name = get_valid_filename(doc.original_filename) or "download"
    try:
        file_handle = doc.file.open("rb")
    except OSError:
        raise Http404
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=safe_name,
    )


@login_required
@require_GET
def engagement_division_query_attachment_download(
    request, division_pk, work_area_pk, query_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    attachment = get_object_or_404(
        AuditQueryAttachment.objects.select_related(
            "query__division_work_area__division"
        ),
        pk=pk,
        query_id=query_pk,
        query__division_work_area_id=work_area_pk,
        query__division_work_area__division_id=division.pk,
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


@login_required
def engagement_status_remarks(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client",
            "fiscal_year",
            "service",
        ),
        pk=engagement_pk,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = (request.POST.get("action") or "").strip()
        if action == "add_remark":
            remarks = (request.POST.get("remarks") or "").strip()
            remark_date = parse_date((request.POST.get("remark_date") or "").strip())
            if remark_date is None:
                messages.error(request, "Enter a valid status remark date.")
            elif not remarks:
                messages.error(request, "Remarks cannot be blank.")
            else:
                EngagementStatusRemark.objects.create(
                    engagement=engagement,
                    remark_date=remark_date,
                    remarks=remarks,
                    created_by=request.user,
                )
                messages.success(request, "Status remark added.")
        return redirect("engagement_status_remarks", engagement_pk=engagement.pk)

    remarks = engagement.status_remarks.select_related("created_by").all()
    team_assignments = engagement.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_status_remarks.html",
        {
            "engagement": engagement,
            "remarks": remarks,
            "team_assignments": team_assignments,
            "default_remark_date": timezone.localdate(),
        },
    )


@login_required
def engagement_division_status_remarks(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = (request.POST.get("action") or "").strip()
        if action == "add_remark":
            remarks = (request.POST.get("remarks") or "").strip()
            remark_date = parse_date((request.POST.get("remark_date") or "").strip())
            if remark_date is None:
                messages.error(request, "Enter a valid status remark date.")
            elif not remarks:
                messages.error(request, "Remarks cannot be blank.")
            else:
                EngagementDivisionStatusRemark.objects.create(
                    division=division,
                    remark_date=remark_date,
                    remarks=remarks,
                    created_by=request.user,
                )
                messages.success(request, "Status remark added.")
        return redirect("engagement_division_status_remarks", division_pk=division.pk)

    remarks = division.status_remarks.select_related("created_by").all()
    team_assignments = division.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_division_status_remarks.html",
        {
            "division": division,
            "remarks": remarks,
            "team_assignments": team_assignments,
            "default_remark_date": timezone.localdate(),
        },
    )


@login_required
def engagement_work_area_status_remarks(request, engagement_pk, work_area_pk):
    return redirect(
        "engagement_work_area_queries",
        engagement_pk=engagement_pk,
        work_area_pk=work_area_pk,
    )


@login_required
def engagement_division_work_area_status_remarks(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = (request.POST.get("action") or "").strip()
        if action == "add_remark":
            remarks = (request.POST.get("remarks") or "").strip()
            remark_date = parse_date((request.POST.get("remark_date") or "").strip())
            if remark_date is None:
                messages.error(request, "Enter a valid status remark date.")
            elif not remarks:
                messages.error(request, "Remarks cannot be blank.")
            else:
                DivisionWorkAreaStatusRemark.objects.create(
                    work_area=work_area,
                    remark_date=remark_date,
                    remarks=remarks,
                    created_by=request.user,
                )
                messages.success(request, "Status remark added.")
        return redirect(
            "engagement_division_work_area_status_remarks",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )
    return redirect(
        "engagement_division_work_area_queries",
        division_pk=division_pk,
        work_area_pk=work_area_pk,
    )


def _division_work_area_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = DivisionWorkAreaForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            with transaction.atomic():
                work_area = form.save(commit=False)
                if instance is None:
                    work_area.division = division
                    work_area.created_by = request.user
                work_area.save()
                _resequence_scoped_work_areas(
                    model=DivisionWorkArea,
                    scope_filter={"division": division},
                    target_pk=work_area.pk,
                    requested_order=form.cleaned_data.get("sort_order"),
                )
            return redirect(
                "engagement_division_work_areas",
                division_pk=division.pk,
            )
    else:
        form = DivisionWorkAreaForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_work_area_form.html",
        {
            "form": form,
            "division": division,
            "work_area": instance,
        },
    )


@login_required
def engagement_division_work_area_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    return _division_work_area_form_view(request, division=division)


@login_required
def engagement_division_work_area_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=pk,
        division=division,
    )
    return _division_work_area_form_view(
        request,
        division=division,
        instance=work_area,
    )


@login_required
def engagement_division_work_area_schedule(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            schedule_row = get_object_or_404(
                DivisionWorkAreaPeriod,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            if (
                not request.user.is_superuser
                and schedule_row.actual_finish is not None
                and not work_area.schedule_rows.exclude(pk=schedule_row.pk).filter(
                    actual_finish__isnull=False
                ).exists()
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed work area.",
                )
                return redirect(
                    "engagement_division_work_area_schedule",
                    division_pk=division.pk,
                    work_area_pk=work_area.pk,
                )
            schedule_row.delete()
            return redirect(
                "engagement_division_work_area_schedule",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_division_work_area_schedule",
            division_pk=division.pk,
            work_area_pk=work_area.pk,
        )

    schedule_rows = work_area.schedule_rows.all()
    return render(
        request,
        "engagements/engagement_division_work_area_schedule.html",
        {
            "division": division,
            "work_area": work_area,
            "schedule_rows": schedule_rows,
        },
    )


def _division_work_area_schedule_form_view(request, division, work_area, instance=None):
    assert_division_open_for_management(request.user, division)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = DivisionWorkAreaPeriodForm(
            request.POST,
            instance=instance,
            work_area=work_area,
        )
        if form.is_valid():
            with transaction.atomic():
                schedule_row = form.save(commit=False)
                if not _can_manage_structure(request.user) and instance is not None:
                    schedule_row.planned_start = original_planned_start
                    schedule_row.planned_finish = original_planned_finish
                if (
                    instance is not None
                    and not request.user.is_superuser
                    and had_actual_finish
                    and schedule_row.actual_finish is None
                    and not work_area.schedule_rows.exclude(pk=instance.pk).filter(
                        actual_finish__isnull=False
                    ).exists()
                ):
                    messages.error(
                        request,
                        "Admin only: reopen closed work area.",
                    )
                    return redirect(
                        "engagement_division_work_area_schedule",
                        division_pk=division.pk,
                        work_area_pk=work_area.pk,
                    )
                if instance is None:
                    schedule_row.work_area = work_area
                    schedule_row.created_by = request.user
                _ensure_engagement_schedule_from_work_area_plan(
                    engagement=division.engagement,
                    planned_start=schedule_row.planned_start,
                    planned_finish=schedule_row.planned_finish,
                    user=request.user,
                )
                schedule_row.save()
            return redirect(
                "engagement_division_work_area_schedule",
                division_pk=division.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = DivisionWorkAreaPeriodForm(instance=instance, work_area=work_area)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    return render(
        request,
        "engagements/engagement_division_work_area_schedule_form.html",
        {
            "form": form,
            "division": division,
            "work_area": work_area,
            "schedule_row": instance,
        },
    )


@login_required
def engagement_division_work_area_schedule_create(request, division_pk, work_area_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    return _division_work_area_schedule_form_view(
        request,
        division=division,
        work_area=work_area,
    )


@login_required
def engagement_division_work_area_schedule_edit(request, division_pk, work_area_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    work_area = get_object_or_404(
        DivisionWorkArea,
        pk=work_area_pk,
        division=division,
    )
    schedule_row = get_object_or_404(
        DivisionWorkAreaPeriod,
        pk=pk,
        work_area=work_area,
    )
    return _division_work_area_schedule_form_view(
        request,
        division=division,
        work_area=work_area,
        instance=schedule_row,
    )


