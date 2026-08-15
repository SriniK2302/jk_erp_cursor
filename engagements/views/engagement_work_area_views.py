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
    _add_engagement_work_areas_from_service_templates,
    _bulk_add_all_standard_work_areas,
    _bulk_delete_work_areas_without_queries,
    _engagement_service_work_area_pick_rows,
    _json_bulk_work_areas_response,
    _mappable_template_ids_not_on_scope,
    _resequence_scoped_work_areas,
    _service_checklist_templates_for_service,
)
from .constants import _WORK_AREA_STATUS_FILTERS

def engagement_work_areas(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    raw_status = (request.GET.get("status") or "active").strip().lower()
    if raw_status not in _WORK_AREA_STATUS_FILTERS:
        raw_status = "active"

    assert_engagement_open_for_management(request.user, engagement)

    def _work_areas_redirect():
        base = reverse("engagement_work_areas", kwargs={"engagement_pk": engagement.pk})
        if raw_status == "all":
            return redirect(f"{base}?{urlencode({'status': raw_status})}")
        return redirect(base)

    if request.method == "POST":
        action = request.POST.get("action")
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
            created = _add_engagement_work_areas_from_service_templates(
                request, engagement, raw_ids
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
            return _work_areas_redirect()
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            work_area = get_object_or_404(
                EngagementWorkArea,
                pk=request.POST.get("pk"),
                engagement=engagement,
            )
            work_area.delete()
            return _work_areas_redirect()
        if action == "bulk_add_all_standard":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            service_template_list = list(
                _service_checklist_templates_for_service(engagement.service_id)
            )
            all_service_pick_rows = _engagement_service_work_area_pick_rows(
                engagement, service_template_list
            )
            stats = _bulk_add_all_standard_work_areas(
                request,
                engagement=engagement,
                pick_rows=all_service_pick_rows,
            )
            msg = (
                f"Added {stats['work_areas_added']} work area(s) and "
                f"{stats['checklist_lines_added']} checklist line(s) to the notes log."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _work_areas_redirect()
        if action == "bulk_delete_all_without_queries":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            stats = _bulk_delete_work_areas_without_queries(engagement=engagement)
            msg = (
                f"Deleted {stats['deleted']} work area(s). "
                f"Kept {stats['skipped_with_queries']} with notes/queries."
            )
            if batch_save_wants_json(request):
                return _json_bulk_work_areas_response(ok=True, message=msg, stats=stats)
            messages.success(request, msg)
            return _work_areas_redirect()
        return _work_areas_redirect()

    work_areas = (
        _engagement_work_area_queryset_for_user(request.user)
        .filter(engagement=engagement)
        .annotate(
            schedule_row_count=Count("schedule_rows"),
            document_count=Count("documents"),
            assignment_count=Count("team_assignments"),
            status_remark_count=Count("status_remarks"),
        )
        .order_by("work_area_name", "sort_order", "id")
    )
    team_assignments = engagement.team_assignments.select_related("team_member").all()
    if raw_status == "active":
        work_areas = work_areas.exclude(status=STATUS_COMPLETED)
    service_template_list = list(
        _service_checklist_templates_for_service(engagement.service_id)
    )
    all_service_pick_rows = _engagement_service_work_area_pick_rows(
        engagement, service_template_list
    )
    service_work_area_pick_rows = [
        r for r in all_service_pick_rows if not r["already_added"]
    ]
    service_standard_template_count = len(service_template_list)
    return render(
        request,
        "engagements/engagement_work_areas.html",
        {
            "engagement": engagement,
            "work_areas": work_areas,
            "team_assignments": team_assignments,
            "work_area_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
            "service_work_area_pick_rows": service_work_area_pick_rows,
            "service_standard_template_count": service_standard_template_count,
        },
    )


@login_required
def engagement_work_area_notes_list(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    rows = (
        AuditQuery.objects.filter(engagement_work_area__engagement=engagement)
        .select_related("engagement_work_area")
        .annotate(response_count=Count("responses"))
        .order_by("-query_date", "-id")
    )
    ctx = work_area_notes_list_page_context(
        engagement=engagement,
        rows=rows,
    )
    return render(request, "engagements/work_area_notes_list.html", ctx)


@login_required
def engagement_all_work_area_notes(request, engagement_pk):
    """Queries/remarks across engagement-level and all division work areas."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    rows = (
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
        "engagements/engagement_all_work_area_notes.html",
        {
            "engagement": engagement,
            "rows": rows,
        },
    )


def _engagement_work_area_form_view(request, engagement, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementWorkAreaForm(
            request.POST,
            instance=instance,
            engagement=engagement,
        )
        if form.is_valid():
            with transaction.atomic():
                work_area = form.save(commit=False)
                if instance is None:
                    work_area.engagement = engagement
                    work_area.created_by = request.user
                work_area.save()
                _resequence_scoped_work_areas(
                    model=EngagementWorkArea,
                    scope_filter={"engagement": engagement},
                    target_pk=work_area.pk,
                    requested_order=form.cleaned_data.get("sort_order"),
                )
            return redirect("engagement_work_areas", engagement_pk=engagement.pk)
    else:
        form = EngagementWorkAreaForm(instance=instance, engagement=engagement)

    return render(
        request,
        "engagements/engagement_work_area_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": instance,
        },
    )


@login_required
def engagement_work_area_create(request, engagement_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    return _engagement_work_area_form_view(request, engagement=engagement)


@login_required
def engagement_work_area_edit(request, engagement_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=pk,
        engagement=engagement,
    )
    return _engagement_work_area_form_view(
        request,
        engagement=engagement,
        instance=work_area,
    )


@login_required
def engagement_work_area_assignments(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    assert_engagement_open_for_management(request.user, engagement)
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            assignment = get_object_or_404(
                EngagementWorkAreaTeamAssignment,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            assignment.delete()
            return redirect(
                "engagement_work_area_assignments",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_work_area_assignments",
            engagement_pk=engagement.pk,
            work_area_pk=work_area.pk,
        )

    assignments = work_area.team_assignments.select_related("team_member")
    return render(
        request,
        "engagements/engagement_work_area_assignments.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "assignments": assignments,
        },
    )


def _engagement_work_area_assignment_form_view(request, engagement, work_area, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementWorkAreaTeamAssignmentForm(
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
                "engagement_work_area_assignments",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = EngagementWorkAreaTeamAssignmentForm(
            instance=instance, work_area=work_area
        )
    return render(
        request,
        "engagements/engagement_work_area_assignment_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": work_area,
            "assignment": instance,
        },
    )


@login_required
def engagement_work_area_assignment_create(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    return _engagement_work_area_assignment_form_view(
        request, engagement=engagement, work_area=work_area
    )


@login_required
def engagement_work_area_assignment_edit(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    assignment = get_object_or_404(
        EngagementWorkAreaTeamAssignment,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_work_area_assignment_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
        instance=assignment,
    )


@login_required
def engagement_work_area_schedule(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    assert_engagement_open_for_management(request.user, engagement)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            schedule_row = get_object_or_404(
                EngagementWorkAreaPeriod,
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
                    "engagement_work_area_schedule",
                    engagement_pk=engagement.pk,
                    work_area_pk=work_area.pk,
                )
            schedule_row.delete()
            return redirect(
                "engagement_work_area_schedule",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        return redirect(
            "engagement_work_area_schedule",
            engagement_pk=engagement.pk,
            work_area_pk=work_area.pk,
        )

    schedule_rows = work_area.schedule_rows.all()
    return render(
        request,
        "engagements/engagement_work_area_schedule.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "schedule_rows": schedule_rows,
        },
    )


def _ensure_engagement_schedule_from_work_area_plan(
    *, engagement, planned_start, planned_finish, user
):
    if not planned_start or not planned_finish:
        return
    if engagement.schedules.exists():
        return
    EngagementSchedule.objects.create(
        engagement=engagement,
        planned_start=planned_start,
        planned_finish=planned_finish,
        actual_start=None,
        actual_finish=None,
        created_by=user,
    )


def _engagement_work_area_schedule_form_view(request, engagement, work_area, instance=None):
    assert_engagement_open_for_management(request.user, engagement)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = EngagementWorkAreaPeriodForm(
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
                        "engagement_work_area_schedule",
                        engagement_pk=engagement.pk,
                        work_area_pk=work_area.pk,
                    )
                if instance is None:
                    schedule_row.work_area = work_area
                    schedule_row.created_by = request.user
                _ensure_engagement_schedule_from_work_area_plan(
                    engagement=engagement,
                    planned_start=schedule_row.planned_start,
                    planned_finish=schedule_row.planned_finish,
                    user=request.user,
                )
                schedule_row.save()
            return redirect(
                "engagement_work_area_schedule",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
    else:
        form = EngagementWorkAreaPeriodForm(instance=instance, work_area=work_area)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    return render(
        request,
        "engagements/engagement_work_area_schedule_form.html",
        {
            "form": form,
            "engagement": engagement,
            "work_area": work_area,
            "schedule_row": instance,
        },
    )


@login_required
def engagement_work_area_schedule_create(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    return _engagement_work_area_schedule_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
    )


@login_required
def engagement_work_area_schedule_edit(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    schedule_row = get_object_or_404(
        EngagementWorkAreaPeriod,
        pk=pk,
        work_area=work_area,
    )
    return _engagement_work_area_schedule_form_view(
        request,
        engagement=engagement,
        work_area=work_area,
        instance=schedule_row,
    )


@login_required
def engagement_work_area_documents(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea,
        pk=work_area_pk,
        engagement=engagement,
    )
    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
    files_redirect = redirect(
        "engagement_work_area_documents",
        engagement_pk=engagement.pk,
        work_area_pk=work_area.pk,
    )
    doc_options = EngagementDocumentation.objects.order_by(
        "standard_document", "document_stage"
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit_document":
            doc = get_object_or_404(
                EngagementWorkAreaDocument,
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
                EngagementWorkAreaDocument,
                pk=request.POST.get("pk"),
                work_area=work_area,
            )
            doc.delete()
            messages.success(request, "Document removed.")
            return files_redirect
        return files_redirect

    documents = work_area.documents.order_by("-document_date", "original_filename", "pk")
    note_attachments = (
        AuditQueryAttachment.objects.filter(query__engagement_work_area=work_area)
        .select_related("query", "created_by")
        .order_by("-created_on", "pk")
    )
    return render(
        request,
        "engagements/engagement_work_area_documents.html",
        {
            "engagement": engagement,
            "work_area": work_area,
            "documents": documents,
            "note_attachments": note_attachments,
            "doc_options": doc_options,
        },
    )


def _apply_edit_query_post(request, query):
    """Shared 'edit note' handler for engagement and division work area notes."""
    subject = (request.POST.get("subject") or "").strip()
    amount_raw = (request.POST.get("amount") or "").strip()
    amount_unit = (request.POST.get("amount_unit") or "").strip().lower()
    query_text = (request.POST.get("query_text") or "").strip()
    expected = (request.POST.get("response_expected_from") or "").strip().lower()
    query_date_raw = (request.POST.get("query_date") or "").strip()
    entry_type = (request.POST.get("entry_type") or "").strip().lower()

    query_date = query.query_date
    if query_date_raw:
        parsed = parse_date(query_date_raw)
        if parsed is None:
            messages.error(request, "Enter a valid note date.")
            return
        query_date = parsed

    if entry_type not in {AuditQuery.ENTRY_TYPE_QUERY, AuditQuery.ENTRY_TYPE_REMARK}:
        entry_type = query.entry_type
    if entry_type != query.entry_type and query.entry_type == AuditQuery.ENTRY_TYPE_QUERY:
        if query.converted_to_working_paper:
            messages.error(
                request,
                "Cannot change the entry type: this query was already converted to a working paper.",
            )
            return
        if query.responses.exists():
            messages.error(
                request,
                "Cannot change the entry type: responses are already recorded against this query.",
            )
            return

    amount = None
    if amount_raw:
        try:
            amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid amount.")
            return
    if expected not in {
        AuditQuery.RESPONDER_INTERNAL,
        AuditQuery.RESPONDER_CLIENT,
    }:
        expected = AuditQuery.RESPONDER_INTERNAL
    if amount_unit not in {
        AuditQuery.AMOUNT_UNIT_LAKHS,
        AuditQuery.AMOUNT_UNIT_RS,
        AuditQuery.AMOUNT_UNIT_CRORES,
    }:
        amount_unit = AuditQuery.AMOUNT_UNIT_LAKHS

    if entry_type == AuditQuery.ENTRY_TYPE_QUERY and not subject:
        messages.error(request, "Query subject cannot be blank.")
        return
    if not query_text:
        messages.error(request, "Query details cannot be blank.")
        return
    if entry_type == AuditQuery.ENTRY_TYPE_REMARK and not subject:
        subject = "Remark"

    query.query_date = query_date
    query.entry_type = entry_type
    query.subject = subject
    query.amount = amount if entry_type == AuditQuery.ENTRY_TYPE_QUERY else None
    query.amount_unit = amount_unit
    query.query_text = query_text
    query.response_expected_from = (
        expected
        if entry_type == AuditQuery.ENTRY_TYPE_QUERY
        else AuditQuery.RESPONDER_INTERNAL
    )
    query.save(
        update_fields=[
            "query_date",
            "entry_type",
            "subject",
            "amount",
            "amount_unit",
            "query_text",
            "response_expected_from",
            "updated_on",
        ]
    )
    messages.success(request, "Note updated.")


@login_required
def engagement_work_area_queries(request, engagement_pk, work_area_pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user).select_related(
            "client", "fiscal_year", "service"
        ),
        pk=engagement_pk,
    )
    work_area = get_object_or_404(
        EngagementWorkArea.objects.select_related(
            "engagement__service",
            "service_checklist_work_area",
        ),
        pk=work_area_pk,
        engagement=engagement,
    )

    if request.method == "POST":
        assert_engagement_open_for_management(request.user, engagement)
        action = (request.POST.get("action") or "").strip()
        if action == "add_query_batch":
            errs = save_work_area_notes_batch(
                request, work_area, engagement_work_area=True
            )
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Notes saved.")
        elif action == "add_all_checklist_lines":
            created, errs = add_all_checklist_lines_to_notes_log(
                request, work_area, engagement_work_area=True
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
                request, work_area, row_index, engagement_work_area=True
            )
            if batch_save_wants_json(request):
                return json_batch_save_response(ok=not errs, errors=errs)
            if errs:
                for msg in errs:
                    messages.error(request, msg)
            else:
                messages.success(request, "Line saved.")
            return redirect(
                "engagement_work_area_queries",
                engagement_pk=engagement.pk,
                work_area_pk=work_area.pk,
            )
        elif action == "add_response":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
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
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
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
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
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
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
            )
            _apply_edit_query_post(request, query)
        elif action == "delete_query":
            query_pk = (request.POST.get("query_pk") or "").strip()
            if not query_pk:
                messages.error(request, "Select a previous query to delete.")
            else:
                query = get_object_or_404(
                    AuditQuery, pk=query_pk, engagement_work_area=work_area
                )
                query.delete()
                messages.success(request, "Note deleted.")
        elif action == "convert_to_working_paper":
            query = get_object_or_404(
                AuditQuery, pk=request.POST.get("query_pk"), engagement_work_area=work_area
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
            "engagement_work_area_queries",
            engagement_pk=engagement.pk,
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
        engagement=engagement,
        engagement_work_area=True,
    )

    ctx["default_date"] = timezone.localdate()
    return render(request, "engagements/work_area_queries.html", ctx)


@login_required
@require_GET
def engagement_work_area_document_download(request, engagement_pk, work_area_pk, pk):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    doc = get_object_or_404(
        EngagementWorkAreaDocument.objects.select_related("work_area__engagement"),
        pk=pk,
        work_area_id=work_area_pk,
        work_area__engagement_id=engagement.pk,
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
def engagement_query_attachment_download(
    request, engagement_pk, work_area_pk, query_pk, pk
):
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user),
        pk=engagement_pk,
    )
    attachment = get_object_or_404(
        AuditQueryAttachment.objects.select_related(
            "query__engagement_work_area__engagement"
        ),
        pk=pk,
        query_id=query_pk,
        query__engagement_work_area_id=work_area_pk,
        query__engagement_work_area__engagement_id=engagement.pk,
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


