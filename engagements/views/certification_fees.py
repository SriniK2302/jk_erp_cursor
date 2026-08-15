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

@login_required
def certification_fees(request):
    from engagements.session_context import get_session_engagement
    from sales.udins.certification_period_fee import bulk_apply_certification_period_fees_to_udins
    from sales.udins.models import CertificationPeriodFee

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "delete":
            row = get_object_or_404(CertificationPeriodFee, pk=request.POST.get("pk"))
            row.delete()
            messages.success(request, "Certification fee period deleted.")
            return redirect("certification_fees")
        if action == "apply_to_udins":
            updated, skipped = bulk_apply_certification_period_fees_to_udins(only_blank=True)
            messages.success(
                request,
                f"Applied certification fees to {updated} UDIN row(s) across all clients. "
                f"Skipped {skipped} row(s) (not Certification, Inv TV already set, or no matching fee).",
            )
            return redirect("certification_fees")
        return redirect("certification_fees")

    rows = CertificationPeriodFee.objects.select_related("client").all()
    session = get_session_engagement(request)
    if session is not None:
        rows = rows.filter(client_id=session.client_id)
    return render(
        request,
        "engagements/certification_fees.html",
        {"rows": rows},
    )


def _certification_fee_form_view(request, instance=None):
    from engagements.session_context import get_session_engagement
    from sales.udins.forms import CertificationPeriodFeeForm

    if request.method == "POST":
        form = CertificationPeriodFeeForm(request.POST, instance=instance)
        if form.is_valid():
            row = form.save()
            from sales.udins.certification_period_fee import bulk_apply_certification_period_fees_to_udins

            updated, skipped = bulk_apply_certification_period_fees_to_udins(
                only_blank=True,
                client_id=row.client_id,
            )
            messages.success(
                request,
                f"Certification fee period saved. Set Inv TV amt on {updated} matching UDIN row(s) "
                f"for {row.client.client_short_name}. Skipped {skipped} row(s).",
            )
            return redirect("certification_fees")
    else:
        initial = {}
        if instance is None:
            session = get_session_engagement(request)
            if session is not None:
                initial["client"] = session.client_id
                if session.fiscal_year_id:
                    initial["from_date"] = session.fiscal_year.start_date
                    initial["to_date"] = session.fiscal_year.end_date
        form = CertificationPeriodFeeForm(instance=instance, initial=initial)
    return render(
        request,
        "engagements/certification_fee_form.html",
        {"form": form, "row": instance},
    )


@login_required
def certification_fee_create(request):
    return _certification_fee_form_view(request)


@login_required
def certification_fee_edit(request, pk):
    from sales.udins.models import CertificationPeriodFee

    row = get_object_or_404(CertificationPeriodFee, pk=pk)
    return _certification_fee_form_view(request, instance=row)
