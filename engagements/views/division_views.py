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

from .constants import (
    _DIVISION_STATUS_LIST_FILTERS,
    _DIVISION_TEAM_LIST_FILTERS,
    _ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY,
    _ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY,
)
from engagements.forms import _engagement_schedule_bounds

def _redirect_engagement_divisions_list(request):
    """Preserve ?team=/status from URL, or fall back to last saved filters."""
    base = reverse("engagement_divisions")
    params = request.GET.copy()
    if "team" not in params:
        saved = request.session.get(_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY, "all")
        if saved in _DIVISION_TEAM_LIST_FILTERS and saved != "all":
            params["team"] = saved
    if "status" not in params:
        saved = request.session.get(_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY, "active")
        if saved in _DIVISION_STATUS_LIST_FILTERS and saved != "active":
            params["status"] = saved
    if params:
        return redirect(f"{base}?{params.urlencode()}")
    return redirect(base)


@login_required
def engagement_divisions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            division = get_object_or_404(
                _engagement_division_queryset_for_user(request.user),
                pk=request.POST.get("pk"),
            )
            division.delete()
            return _redirect_engagement_divisions_list(request)
        return _redirect_engagement_divisions_list(request)

    team_param = request.GET.get("team")
    if team_param is not None:
        raw_team = team_param.strip().lower()
        if raw_team not in _DIVISION_TEAM_LIST_FILTERS:
            raw_team = "all"
        request.session[_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY] = raw_team
    else:
        raw_team = request.session.get(_ENGAGEMENT_DIVISIONS_TEAM_SESSION_KEY, "all")
        if raw_team not in _DIVISION_TEAM_LIST_FILTERS:
            raw_team = "all"

    status_param = request.GET.get("status")
    if status_param is not None:
        raw_status = status_param.strip().lower()
        if raw_status not in _DIVISION_STATUS_LIST_FILTERS:
            raw_status = "active"
        request.session[_ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY] = raw_status
    else:
        raw_status = request.session.get(
            _ENGAGEMENT_DIVISIONS_STATUS_SESSION_KEY, "active"
        )
        if raw_status not in _DIVISION_STATUS_LIST_FILTERS:
            raw_status = "active"

    divisions = (
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        )
        .annotate(
            division_work_area_count=Count("work_areas", distinct=True),
            documentation_count=Count("documentation_maps", distinct=True),
            team_assignment_count=Count("team_assignments", distinct=True),
            status_remark_count=Count("status_remarks", distinct=True),
        )
    )
    if not request.user.is_superuser:
        divisions = divisions.exclude(engagement__status=STATUS_COMPLETED)
    if raw_status == "active":
        divisions = divisions.exclude(status=STATUS_COMPLETED)
    if raw_team == "unassigned":
        divisions = divisions.filter(team_assignment_count=0)
    divisions = filter_by_engagement_id(divisions, request, "engagement_id")

    return render(
        request,
        "engagements/engagement_divisions.html",
        {
            "divisions": divisions,
            "division_team_filter": raw_team,
            "division_status_filter": raw_status,
            "active_timer_scope": _timer_scope_dict(_active_time_session_for_user(request.user)),
        },
    )


@login_required
@require_GET
def engagement_schedule_bounds_json(request, engagement_pk):
    """Min planned start and max planned finish across engagement schedule rows (for division form autofill)."""
    engagement = get_object_or_404(
        _engagement_queryset_for_user(request.user), pk=engagement_pk
    )
    assert_engagement_open_for_management(request.user, engagement)
    earliest_start, latest_finish = _engagement_schedule_bounds(engagement)
    return JsonResponse(
        {
            "planned_start": earliest_start.isoformat() if earliest_start else None,
            "planned_finish": latest_finish.isoformat() if latest_finish else None,
        }
    )


def _engagement_division_form_view(request, instance=None):
    if instance is not None:
        assert_division_open_for_management(request.user, instance)
    if instance is None and not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        had_actual_finish = instance is not None and instance.actual_finish is not None
        original_engagement = instance.engagement if instance is not None else None
        original_division_name = instance.division_name if instance is not None else None
        original_planned_start = instance.planned_start if instance is not None else None
        original_planned_finish = instance.planned_finish if instance is not None else None
        form = EngagementDivisionForm(request.POST, instance=instance)
        if form.is_valid():
            if instance is None:
                cand_eng = form.cleaned_data.get("engagement")
                assert_engagement_open_for_management(request.user, cand_eng)
            division = form.save(commit=False)
            if not _can_manage_structure(request.user) and instance is not None:
                division.engagement = original_engagement
                division.division_name = original_division_name
                division.planned_start = original_planned_start
                division.planned_finish = original_planned_finish
            if (
                instance is not None
                and not request.user.is_superuser
                and had_actual_finish
                and division.actual_finish is None
            ):
                messages.error(
                    request,
                    "Admin only: reopen closed division.",
                )
                return redirect("engagement_division_edit", pk=instance.pk)
            if instance is None:
                division.created_by = request.user
            division.save()
            return redirect("engagement_divisions")
    else:
        form = EngagementDivisionForm(instance=instance)
        if not _can_manage_structure(request.user) and instance is not None:
            form.fields["engagement"].disabled = True
            form.fields["division_name"].disabled = True
            form.fields["planned_start"].disabled = True
            form.fields["planned_finish"].disabled = True

    team_assignments = []
    if instance is not None:
        team_assignments = list(
            instance.team_assignments.select_related("team_member").all()
        )

    return render(
        request,
        "engagements/engagement_division_form.html",
        {
            "form": form,
            "division": instance,
            "team_assignments": team_assignments,
        },
    )


@login_required
def engagement_division_create(request):
    return _engagement_division_form_view(request)


@login_required
def engagement_division_edit(request, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=pk
    )
    return _engagement_division_form_view(request, instance=division)


@login_required
def engagement_division_team_assignments(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            assignment = get_object_or_404(
                EngagementDivisionTeamAssignment,
                pk=request.POST.get("pk"),
                division=division,
            )
            assignment.delete()
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
        if action == "send_assignment_mail":
            assignment = get_object_or_404(
                EngagementDivisionTeamAssignment,
                pk=request.POST.get("pk"),
                division=division,
            )
            team_mail.manual_notify_division_team_assignment(request, assignment)
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
        return redirect("engagement_division_team_assignments", division_pk=division.pk)

    team_assignments = division.team_assignments.select_related("team_member").all()
    return render(
        request,
        "engagements/engagement_division_team_assignments.html",
        {
            "division": division,
            "team_assignments": team_assignments,
            "today": timezone.localdate(),
        },
    )


def _engagement_division_team_assignment_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if not _can_manage_structure(request.user):
        raise PermissionDenied("Admin only: structural changes are restricted.")
    if request.method == "POST":
        form = EngagementDivisionTeamAssignmentForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            if instance is None:
                assignment.division = division
                assignment.created_by = request.user
            assignment.save()
            team_mail.maybe_auto_notify_division_team_assignment(request, assignment)
            return redirect(
                "engagement_division_team_assignments",
                division_pk=division.pk,
            )
    else:
        form = EngagementDivisionTeamAssignmentForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_team_assignment_form.html",
        {
            "form": form,
            "division": division,
            "assignment": instance,
        },
    )


@login_required
def engagement_division_team_assignment_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    return _engagement_division_team_assignment_form_view(request, division=division)


@login_required
def engagement_division_team_assignment_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user), pk=division_pk
    )
    assignment = get_object_or_404(
        EngagementDivisionTeamAssignment,
        pk=pk,
        division=division,
    )
    return _engagement_division_team_assignment_form_view(
        request,
        division=division,
        instance=assignment,
    )


@login_required
def engagement_division_documentation_maps(request, division_pk):
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
    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "copy_from_division":
            if not _can_manage_structure(request.user):
                raise PermissionDenied("Admin only: structural changes are restricted.")
            source_division_id = (request.POST.get("source_division_id") or "").strip()
            if not source_division_id:
                messages.error(request, "Select a source division.")
                return redirect(
                    "engagement_division_documentation_maps",
                    division_pk=division.pk,
                )
            source_division = eligible_source_divisions.filter(pk=source_division_id).first()
            if source_division is None:
                messages.error(
                    request,
                    (
                        "Selected source division is invalid. Choose one with the same "
                        "client, service, and fiscal year."
                    ),
                )
                return redirect(
                    "engagement_division_documentation_maps",
                    division_pk=division.pk,
                )
            with transaction.atomic():
                existing_ids = set(
                    EngagementDivisionDocumentationMap.objects.filter(
                        division=division
                    ).values_list("documentation_id", flat=True)
                )
                source_maps = source_division.documentation_maps.select_related(
                    "documentation"
                ).order_by(
                    "documentation__document_stage",
                    "documentation__standard_document",
                )
                new_maps = [
                    EngagementDivisionDocumentationMap(
                        division=division,
                        documentation=source_map.documentation,
                        created_by=request.user,
                    )
                    for source_map in source_maps
                    if source_map.documentation_id not in existing_ids
                ]
                created_count = len(new_maps)
                if new_maps:
                    EngagementDivisionDocumentationMap.objects.bulk_create(new_maps)
            if created_count:
                messages.success(
                    request,
                    (
                        f"Copied {created_count} documentation mapping(s) from "
                        f"{source_division.division_name}."
                    ),
                )
            else:
                messages.info(
                    request,
                    "No new documentation mappings to copy from the selected division.",
                )
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        if action == "delete":
            documentation_map = get_object_or_404(
                EngagementDivisionDocumentationMap,
                pk=request.POST.get("pk"),
                division=division,
            )
            documentation_map.delete()
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        if action == "delete_all_documentation_maps":
            qs = division.documentation_maps.all()
            n = qs.count()
            if n:
                with transaction.atomic():
                    qs.delete()
                messages.success(
                    request,
                    (
                        f"Removed {n} division documentation mapping(s) "
                        "(including uploaded files under each mapping)."
                    ),
                )
            else:
                messages.info(request, "No division documentation mappings to remove.")
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
        return redirect("engagement_division_documentation_maps", division_pk=division.pk)

    documentation_maps = division.documentation_maps.select_related("documentation").annotate(
        attachment_count=Count("attachments", distinct=True)
    )
    source_divisions = eligible_source_divisions.order_by(
        "engagement__client__client_name",
        "-engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "division_name",
    )
    return render(
        request,
        "engagements/engagement_division_documentation_maps.html",
        {
            "division": division,
            "documentation_maps": documentation_maps,
            "source_divisions": source_divisions,
        },
    )


@login_required
def engagement_division_documentation_map_files(request, division_pk, map_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client",
            "engagement__fiscal_year",
            "engagement__service",
        ),
        pk=division_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDivisionDocumentationMap.objects.select_related("documentation"),
        pk=map_pk,
        division=division,
    )
    files_redirect = redirect(
        "engagement_division_documentation_map_files",
        division_pk=division.pk,
        map_pk=documentation_map.pk,
    )

    if request.method == "POST":
        assert_division_open_for_management(request.user, division)
        action = request.POST.get("action")
        if action == "upload_attachment":
            files = request.FILES.getlist("files")
            doc_date = parse_date((request.POST.get("document_date") or "").strip())
            description = (request.POST.get("description") or "").strip()
            if doc_date is None:
                messages.error(request, "Document date is required.")
                return files_redirect
            if not files:
                messages.warning(request, "No files were selected.")
                return files_redirect
            n = 0
            with transaction.atomic():
                for upload in files[:30]:
                    EngagementDivisionDocumentationMapAttachment.objects.create(
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
                EngagementDivisionDocumentationMapAttachment,
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
        "engagements/engagement_division_documentation_map_files.html",
        {
            "division": division,
            "documentation_map": documentation_map,
            "attachments": attachments,
        },
    )


@login_required
@require_GET
def engagement_division_documentation_attachment_download(
    request, division_pk, map_pk, pk
):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user),
        pk=division_pk,
    )
    attachment = get_object_or_404(
        EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division"
        ),
        pk=pk,
        documentation_map_id=map_pk,
        documentation_map__division_id=division.pk,
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
@require_GET
def engagement_division_documentation_option_search(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    assert_division_open_for_management(request.user, division)
    q = (request.GET.get("q") or "").strip()
    current_id = (request.GET.get("for_user") or "").strip()

    used_ids = EngagementDivisionDocumentationMap.objects.filter(
        division=division
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
        division.engagement.client,
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


def _engagement_division_documentation_map_form_view(request, division, instance=None):
    assert_division_open_for_management(request.user, division)
    if request.method == "POST":
        form = EngagementDivisionDocumentationMapForm(
            request.POST,
            instance=instance,
            division=division,
        )
        if form.is_valid():
            selected_docs = form.cleaned_data.get("documentation")
            if instance is None and hasattr(selected_docs, "__iter__") and not isinstance(selected_docs, EngagementDocumentation):
                existing_ids = set(
                    EngagementDivisionDocumentationMap.objects.filter(
                        division=division
                    ).values_list("documentation_id", flat=True)
                )
                new_maps = [
                    EngagementDivisionDocumentationMap(
                        division=division,
                        documentation=doc,
                        created_by=request.user,
                    )
                    for doc in selected_docs
                    if doc.pk not in existing_ids
                ]
                if new_maps:
                    with transaction.atomic():
                        EngagementDivisionDocumentationMap.objects.bulk_create(new_maps)
            else:
                with transaction.atomic():
                    documentation_map = form.save(commit=False)
                    if instance is None:
                        documentation_map.division = division
                        documentation_map.created_by = request.user
                    documentation_map.save()
            return redirect(
                "engagement_division_documentation_maps",
                division_pk=division.pk,
            )
    else:
        form = EngagementDivisionDocumentationMapForm(instance=instance, division=division)

    return render(
        request,
        "engagements/engagement_division_documentation_map_form.html",
        {
            "form": form,
            "division": division,
            "documentation_map": instance,
            "add_documentation_url": reverse("engagement_documentation_create")
            + "?"
            + urlencode({"next": request.get_full_path()}),
        },
    )


@login_required
def engagement_division_documentation_map_create(request, division_pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    return _engagement_division_documentation_map_form_view(request, division=division)


@login_required
def engagement_division_documentation_map_edit(request, division_pk, pk):
    division = get_object_or_404(
        _engagement_division_queryset_for_user(request.user).select_related(
            "engagement__client", "engagement__client__classification"
        ),
        pk=division_pk,
    )
    documentation_map = get_object_or_404(
        EngagementDivisionDocumentationMap,
        pk=pk,
        division=division,
    )
    return _engagement_division_documentation_map_form_view(
        request,
        division=division,
        instance=documentation_map,
    )


