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

def _work_area_display_name_from_service_template(template):
    text = (template.name or "").strip()
    return text[:150]


def _service_checklist_templates_for_service(service_id: int):
    return (
        ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id)
        .annotate(checklist_line_count=Count("items"))
        .order_by("sort_order", "id")
    )


def _service_work_area_pick_rows(wa_qs, templates):
    existing_fk = set(
        wa_qs.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in wa_qs.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    rows = []
    for t in templates:
        name_cf = (t.name or "").strip().casefold()
        already = t.pk in existing_fk or (name_cf and name_cf in existing_names_cf)
        line_count = getattr(t, "checklist_line_count", None)
        if line_count is None:
            line_count = t.items.count()
        rows.append(
            {
                "template": t,
                "already_added": already,
                "checklist_line_count": line_count,
                "can_map": line_count > 0,
            }
        )
    return rows


def _engagement_service_work_area_pick_rows(engagement, templates):
    return _service_work_area_pick_rows(
        EngagementWorkArea.objects.filter(engagement=engagement),
        templates,
    )


def _division_service_work_area_pick_rows(division, templates):
    return _service_work_area_pick_rows(
        DivisionWorkArea.objects.filter(division=division),
        templates,
    )


def _add_engagement_work_areas_from_service_templates(request, engagement, template_ids):
    if not template_ids:
        return 0
    templates = list(
        ServiceEngagementChecklistWorkArea.objects.filter(
            pk__in=template_ids,
            service_id=engagement.service_id,
        ).annotate(checklist_line_count=Count("items"))
    )
    if not templates:
        return 0
    existing_q = EngagementWorkArea.objects.filter(engagement=engagement)
    existing_fk = set(
        existing_q.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in existing_q.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    created = 0
    with transaction.atomic():
        for tpl in templates:
            if getattr(tpl, "checklist_line_count", 0) < 1:
                continue
            if tpl.pk in existing_fk:
                continue
            wa_name = _work_area_display_name_from_service_template(tpl)
            if not wa_name:
                continue
            name_cf = wa_name.casefold()
            if name_cf in existing_names_cf:
                continue
            EngagementWorkArea.objects.create(
                engagement=engagement,
                work_area_name=wa_name,
                sort_order=9999,
                created_by=request.user,
                service_checklist_work_area=tpl,
            )
            existing_fk.add(tpl.pk)
            existing_names_cf.add(name_cf)
            created += 1
        if created:
            ordered_ids = list(
                EngagementWorkArea.objects.filter(engagement=engagement)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                EngagementWorkArea.objects.filter(pk=pk).update(sort_order=idx)
    return created


def _add_division_work_areas_from_service_templates(request, division, template_ids):
    if not template_ids:
        return 0
    service_id = division.engagement.service_id
    templates = list(
        ServiceEngagementChecklistWorkArea.objects.filter(
            pk__in=template_ids,
            service_id=service_id,
        ).annotate(checklist_line_count=Count("items"))
    )
    if not templates:
        return 0
    existing_q = DivisionWorkArea.objects.filter(division=division)
    existing_fk = set(
        existing_q.filter(service_checklist_work_area_id__isnull=False).values_list(
            "service_checklist_work_area_id", flat=True
        )
    )
    existing_names_cf = {
        (n or "").strip().casefold()
        for n in existing_q.values_list("work_area_name", flat=True)
        if (n or "").strip()
    }
    created = 0
    with transaction.atomic():
        for tpl in templates:
            if getattr(tpl, "checklist_line_count", 0) < 1:
                continue
            if tpl.pk in existing_fk:
                continue
            wa_name = _work_area_display_name_from_service_template(tpl)
            if not wa_name:
                continue
            name_cf = wa_name.casefold()
            if name_cf in existing_names_cf:
                continue
            DivisionWorkArea.objects.create(
                division=division,
                work_area_name=wa_name,
                sort_order=9999,
                created_by=request.user,
                service_checklist_work_area=tpl,
            )
            existing_fk.add(tpl.pk)
            existing_names_cf.add(name_cf)
            created += 1
        if created:
            ordered_ids = list(
                DivisionWorkArea.objects.filter(division=division)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)
    return created


def _mappable_template_ids_not_on_scope(pick_rows) -> list[int]:
    return [
        row["template"].pk
        for row in pick_rows
        if row.get("can_map") and not row.get("already_added")
    ]


def _bulk_add_all_standard_work_areas(
    request,
    *,
    engagement=None,
    division=None,
    pick_rows,
) -> dict[str, int]:
    template_ids = _mappable_template_ids_not_on_scope(pick_rows)
    work_areas_added = 0
    checklist_lines_added = 0

    with transaction.atomic():
        if engagement is not None:
            work_areas_added = _add_engagement_work_areas_from_service_templates(
                request, engagement, template_ids
            )
            work_area_qs = EngagementWorkArea.objects.filter(
                engagement=engagement
            )
            engagement_work_area = True
        else:
            work_areas_added = _add_division_work_areas_from_service_templates(
                request, division, template_ids
            )
            work_area_qs = DivisionWorkArea.objects.filter(division=division)
            engagement_work_area = False

        for work_area in work_area_qs:
            if not work_area_has_checklist_template(work_area):
                continue
            created, _errs = add_all_checklist_lines_to_notes_log(
                request,
                work_area,
                engagement_work_area=engagement_work_area,
            )
            checklist_lines_added += created

    return {
        "work_areas_added": work_areas_added,
        "checklist_lines_added": checklist_lines_added,
    }


def _bulk_delete_work_areas_without_queries(
    *,
    engagement=None,
    division=None,
) -> dict[str, int]:
    if engagement is not None:
        qs = EngagementWorkArea.objects.filter(engagement=engagement)
    else:
        qs = DivisionWorkArea.objects.filter(division=division)

    annotated = qs.annotate(query_count=Count("audit_queries"))
    to_delete = annotated.filter(query_count=0)
    skipped_with_queries = annotated.filter(query_count__gt=0).count()
    deleted = to_delete.count()

    with transaction.atomic():
        to_delete.delete()
        if engagement is not None:
            ordered_ids = list(
                EngagementWorkArea.objects.filter(engagement=engagement)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                EngagementWorkArea.objects.filter(pk=pk).update(sort_order=idx)
        else:
            ordered_ids = list(
                DivisionWorkArea.objects.filter(division=division)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
            )
            for idx, pk in enumerate(ordered_ids, start=1):
                DivisionWorkArea.objects.filter(pk=pk).update(sort_order=idx)

    return {
        "deleted": deleted,
        "skipped_with_queries": skipped_with_queries,
    }


def _resequence_scoped_work_areas(*, model, scope_filter, target_pk, requested_order):
    siblings = list(
        model.objects.filter(**scope_filter)
        .exclude(pk=target_pk)
        .order_by("sort_order", "id")
        .values_list("pk", flat=True)
    )
    total = len(siblings) + 1
    try:
        position = int(requested_order or total)
    except (TypeError, ValueError):
        position = total
    position = max(1, min(position, total))

    ordered_ids = siblings.copy()
    ordered_ids.insert(position - 1, target_pk)
    for idx, pk in enumerate(ordered_ids, start=1):
        model.objects.filter(pk=pk).update(sort_order=idx)


def _json_bulk_work_areas_response(*, ok: bool, message: str = "", stats: dict | None = None, status: int = 200):
    payload = {"ok": ok, "message": message}
    if stats:
        payload.update(stats)
    if not ok:
        return JsonResponse(payload, status=status if status != 200 else 400)
    return JsonResponse(payload, status=status)


