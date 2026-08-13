from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Prefetch
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode

from engagements.models import (
    ServiceEngagementChecklistItem,
    ServiceEngagementChecklistWorkArea,
)
from sales.services.models import Service


def _can_edit_service_checklists(user):
    from config.views import MODULE_ENGAGEMENTS, MODULE_SETUP, _has_module_access

    if not user.is_authenticated:
        return False
    return _has_module_access(user, MODULE_SETUP) or _has_module_access(
        user, MODULE_ENGAGEMENTS
    )


def _checklist_url(service_id: int, *, work_area_pk=None, new=False) -> str:
    q: dict[str, str] = {"service": str(service_id)}
    if new:
        q["work_area"] = "new"
    elif work_area_pk is not None:
        q["work_area"] = str(int(work_area_pk))
    return f"{reverse('engagement_checklist_templates')}?{urlencode(q)}"


@login_required
def service_engagement_checklists(request):
    if not _can_edit_service_checklists(request.user):
        raise PermissionDenied(
            "You need Setup or Engagements access to manage engagement checklists."
        )

    services = list(Service.objects.order_by("service_desc"))
    if not services:
        return render(
            request,
            "engagements/checklists/service_checklists.html",
            {"services": [], "no_services": True},
        )

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            service_id = int(request.POST.get("service_id") or "0")
        except ValueError:
            service_id = 0
        if not Service.objects.filter(pk=service_id).exists():
            messages.error(request, "Invalid service.")
            return redirect("engagement_checklist_templates")

        if action == "add_work_area":
            name = (request.POST.get("work_area_name") or "").strip() or "Work area"
            max_so = (
                ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id)
                .aggregate(m=Max("sort_order"))
                .get("m")
            )
            next_so = (max_so or 0) + 1
            created = ServiceEngagementChecklistWorkArea.objects.create(
                service_id=service_id,
                name=name[:200],
                sort_order=next_so,
                created_by=request.user,
            )
            messages.success(request, "Work area saved.")
            return redirect(_checklist_url(service_id, work_area_pk=created.pk))

        if action == "delete_work_area":
            wa = get_object_or_404(
                ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id),
                pk=request.POST.get("work_area_id"),
            )
            wa.delete()
            messages.success(request, "Work area removed.")
            nxt = (
                ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id)
                .order_by("sort_order", "id")
                .values_list("pk", flat=True)
                .first()
            )
            if nxt:
                return redirect(_checklist_url(service_id, work_area_pk=nxt))
            return redirect(_checklist_url(service_id))

        if action == "rename_work_area":
            wa = get_object_or_404(
                ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id),
                pk=request.POST.get("work_area_id"),
            )
            name = (request.POST.get("work_area_name") or "").strip()
            if not name:
                messages.warning(request, "Work area name cannot be empty.")
            else:
                wa.name = name[:200]
                wa.save(update_fields=["name", "updated_on"])
                messages.success(request, "Work area updated.")
            return redirect(_checklist_url(service_id, work_area_pk=wa.pk))

        if action == "add_item":
            wa = get_object_or_404(
                ServiceEngagementChecklistWorkArea.objects.filter(service_id=service_id),
                pk=request.POST.get("work_area_id"),
            )
            line = (request.POST.get("item_line") or "").strip()
            if not line:
                messages.warning(request, "Enter text for the checklist item.")
            else:
                max_so = (
                    ServiceEngagementChecklistItem.objects.filter(work_area=wa)
                    .aggregate(m=Max("sort_order"))
                    .get("m")
                )
                ServiceEngagementChecklistItem.objects.create(
                    work_area=wa,
                    line_text=line[:500],
                    sort_order=(max_so or 0) + 1,
                    created_by=request.user,
                )
                messages.success(request, "Checklist item added.")
            return redirect(_checklist_url(service_id, work_area_pk=wa.pk))

        if action == "update_item":
            item = get_object_or_404(
                ServiceEngagementChecklistItem.objects.select_related("work_area"),
                pk=request.POST.get("item_id"),
            )
            if item.work_area.service_id != service_id:
                raise PermissionDenied("Invalid item for this service.")
            line = (request.POST.get("item_line") or "").strip()
            if not line:
                messages.warning(request, "Checklist item text cannot be empty.")
            else:
                item.line_text = line[:500]
                item.save(update_fields=["line_text", "updated_on"])
                messages.success(request, "Checklist item saved.")
            return redirect(_checklist_url(service_id, work_area_pk=item.work_area_id))

        if action == "delete_item":
            item = get_object_or_404(
                ServiceEngagementChecklistItem.objects.select_related("work_area"),
                pk=request.POST.get("item_id"),
            )
            if item.work_area.service_id != service_id:
                raise PermissionDenied("Invalid item for this service.")
            wa_pk = item.work_area_id
            item.delete()
            messages.success(request, "Checklist item removed.")
            return redirect(_checklist_url(service_id, work_area_pk=wa_pk))

        return redirect(_checklist_url(service_id))

    raw_sid = (request.GET.get("service") or "").strip()
    selected_id = None
    if raw_sid.isdigit():
        cand = int(raw_sid)
        if Service.objects.filter(pk=cand).exists():
            selected_id = cand
    if selected_id is None:
        selected_id = services[0].pk

    wa_base = ServiceEngagementChecklistWorkArea.objects.filter(
        service_id=selected_id
    ).order_by(Lower("name"), "id")
    wa_spinner_list = list(wa_base.only("id", "name"))

    raw_focus = (request.GET.get("work_area") or "").strip().lower()
    is_new_work_area = raw_focus == "new"

    focused_work_area = None
    if not is_new_work_area:
        focus_pk = None
        if raw_focus.isdigit():
            cand_pk = int(raw_focus)
            if wa_base.filter(pk=cand_pk).exists():
                focus_pk = cand_pk
        if focus_pk is None and wa_spinner_list:
            focus_pk = wa_spinner_list[0].pk
        if focus_pk is not None:
            focused_work_area = (
                ServiceEngagementChecklistWorkArea.objects.filter(
                    service_id=selected_id, pk=focus_pk
                )
                .prefetch_related(
                    Prefetch(
                        "items",
                        queryset=ServiceEngagementChecklistItem.objects.order_by(
                            "sort_order", "id"
                        ),
                    )
                )
                .first()
            )

    prev_wa_url = None
    next_wa_url = None
    if focused_work_area is not None and wa_spinner_list:
        ids = [w.pk for w in wa_spinner_list]
        try:
            idx = ids.index(focused_work_area.pk)
        except ValueError:
            idx = 0
        if idx > 0:
            prev_wa_url = _checklist_url(selected_id, work_area_pk=ids[idx - 1])
        if idx < len(ids) - 1:
            next_wa_url = _checklist_url(selected_id, work_area_pk=ids[idx + 1])

    new_work_area_url = _checklist_url(selected_id, new=True)

    return render(
        request,
        "engagements/checklists/service_checklists.html",
        {
            "services": services,
            "selected_service_id": selected_id,
            "work_area_spinner_list": wa_spinner_list,
            "focused_work_area": focused_work_area,
            "is_new_work_area": is_new_work_area,
            "prev_wa_url": prev_wa_url,
            "next_wa_url": next_wa_url,
            "new_work_area_url": new_work_area_url,
            "no_services": False,
        },
    )
