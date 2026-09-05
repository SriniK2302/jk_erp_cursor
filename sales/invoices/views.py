from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.decorators.http import require_GET

from gl.fiscal_years.fy_calendar import fy_no_from_calendar_date
from gl.fiscal_years.models import FiscalYear
from sales.clients.models import Client
from sales.udins.models import Udin

from .forms import (
    InvUdinMapFormSet,
    InvoiceForm,
    persist_maps_and_lines,
    udin_choice_queryset_for_invoice,
)
from .invoice_lines import (
    build_invoice_lines_from_map_entries,
    gross_from_lines,
    money2,
    taxes_total_from_lines,
)
from .invoice_numbers import next_invoice_no
from .models import InvUdinMap, Invoice, InvoiceStatus
from .sales_gl_posting import bulk_post_fresh_invoices_to_gl
from .gstr1_export import EXPORT_FORMATS, gstr1_export_http_response
from .gstr1_invoice_list import (
    compute_gstr1_invoice_list,
    default_month_first_for_fy,
    fy_month_select_options,
    parse_month_param,
    window_for_fy_month,
)
from .monthly_invoice_summary import compute_monthly_invoice_summary
from .sales_ledger_tb import (
    STATUS_SCOPE_CHOICES,
    compute_sales_ledger_tb,
)
from .narration_build import narration_suggestion_for_udin
from .permissions import require_setup_module as _require_setup_module
from .preview_context import build_invoice_preview_context
from .udin_map_sync import sync_udin_flags_for_pks

MAP_FORMSET_PREFIX = "maps"


def _invoice_nav_neighbors(inv):
    """Chronological neighbours (same as date-ASC on the grid): Previous = earlier, Next = later."""
    if inv is None:
        return None, None
    qs = Invoice.objects.all()
    earlier = (
        qs.filter(
            Q(invoice_date__lt=inv.invoice_date)
            | Q(invoice_date=inv.invoice_date, id__lt=inv.id)
        )
        .order_by("-invoice_date", "-id")
        .first()
    )
    later = (
        qs.filter(
            Q(invoice_date__gt=inv.invoice_date)
            | Q(invoice_date=inv.invoice_date, id__gt=inv.id)
        )
        .order_by("invoice_date", "id")
        .first()
    )
    return earlier, later


def _udin_choice_meta(qs):
    meta = {}
    for u in qs.select_related("client", "service"):
        meta[str(u.pk)] = {
            "hasTv": u.inv_tv_amount is not None,
            "tv": "" if u.inv_tv_amount is None else str(u.inv_tv_amount),
            "client": u.client.client_short_name,
            "client_id": u.client_id,
            "client_code": u.client.client_code,
            "service": u.service.service_desc,
            "service_code": u.service.service_code,
            "invoice_tax_type": u.client.invoice_tax_type,
            "narration_suggestion": narration_suggestion_for_udin(u),
            "default_line_desc": u.service.service_desc,
            "udin_remarks": (u.service_remarks or u.remarks or "").strip(),
            "ay_fy": (u.ay_fy or "").strip(),
            "inv_date": u.inv_date.isoformat() if u.inv_date else "",
        }
    return meta


def _map_formset_for_request(*, data, instance: Invoice | None):
    invoice_pk = instance.pk if instance else None
    initial = []
    if instance:
        initial = [
            {
                "udin": m.udin_id,
                "service_desc": m.service_desc,
                "line_amount": m.line_amount,
            }
            for m in instance.inv_udin_maps.order_by("line_no")
        ]
    kwargs = {"initial": initial, "prefix": MAP_FORMSET_PREFIX, "invoice_pk": invoice_pk}
    if data is not None:
        return InvUdinMapFormSet(data, **kwargs)
    return InvUdinMapFormSet(**kwargs)


@login_required
def sales_hub(request):
    _require_setup_module(request)
    return render(request, "invoices/sales_hub.html")


@login_required
def reports_home(request):
    _require_setup_module(request)
    return render(request, "invoices/reports.html")


def _fiscal_year_containing_date(d: date) -> FiscalYear | None:
    """Prefer master dates; fall back to FY label from Indian April–March calendar."""
    fy = (
        FiscalYear.objects.filter(start_date__lte=d, end_date__gte=d)
        .order_by("-fy_no")
        .first()
    )
    if fy is not None:
        return fy
    label = fy_no_from_calendar_date(d)
    return FiscalYear.objects.filter(fy_no__iexact=label).first()


@login_required
def reports_sales_ledger_tb(request):
    _require_setup_module(request)
    today = timezone.localdate()
    current_fy = _fiscal_year_containing_date(today)
    fiscal_years = list(FiscalYear.objects.all())

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    submitted = request.GET.get("fy") is not None

    status_filter = (request.GET.get("status") or "all").strip().lower()
    if status_filter not in STATUS_SCOPE_CHOICES:
        status_filter = "all"

    tb = None
    if submitted and selected_fy is not None:
        tb = compute_sales_ledger_tb(selected_fy, invoice_status=status_filter)

    return render(
        request,
        "invoices/reports_sales_ledger_tb.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "report_submitted": submitted,
            "status_filter": status_filter,
            "tb": tb,
        },
    )


@login_required
def reports_monthly_summary(request):
    _require_setup_module(request)
    today = timezone.localdate()
    current_fy = _fiscal_year_containing_date(today)
    fiscal_years = list(FiscalYear.objects.all())

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    submitted = request.GET.get("fy") is not None

    status_filter = (request.GET.get("status") or "all").strip().lower()
    if status_filter not in STATUS_SCOPE_CHOICES:
        status_filter = "all"

    month_rows = None
    total_row = None
    if submitted and selected_fy is not None:
        month_rows, total_row = compute_monthly_invoice_summary(
            selected_fy,
            invoice_status=status_filter,
        )

    return render(
        request,
        "invoices/reports_monthly_summary.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "report_submitted": submitted,
            "status_filter": status_filter,
            "month_rows": month_rows,
            "total_row": total_row,
        },
    )


@login_required
def reports_gstr1_invoice_list(request):
    _require_setup_module(request)
    today = timezone.localdate()
    current_fy = _fiscal_year_containing_date(today)
    fiscal_years = list(FiscalYear.objects.all())

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    submitted = request.GET.get("fy") is not None

    status_filter = (request.GET.get("status") or "all").strip().lower()
    if status_filter not in STATUS_SCOPE_CHOICES:
        status_filter = "all"

    ytd = request.GET.get("ytd") == "on"

    month_options: list[dict[str, str]] = []
    selected_month_value = ""
    if selected_fy:
        month_options = fy_month_select_options(selected_fy)
        parsed = parse_month_param(request.GET.get("month"), selected_fy)
        month_first = parsed if parsed is not None else default_month_first_for_fy(selected_fy, today)
        selected_month_value = month_first.isoformat()[:7]

    report_rows = None
    window = None
    if submitted and selected_fy is not None and selected_month_value:
        mf = parse_month_param(selected_month_value, selected_fy)
        if mf is None:
            mf = default_month_first_for_fy(selected_fy, today)
        window = window_for_fy_month(selected_fy, month_first=mf, ytd=ytd)
        report_rows = compute_gstr1_invoice_list(
            window.date_from,
            window.date_to,
            invoice_status=status_filter,
        )

    export_fmt = (request.GET.get("export") or "").strip().lower()
    if (
        report_rows is not None
        and window is not None
        and selected_fy is not None
        and export_fmt in EXPORT_FORMATS
    ):
        fn = f"gstr1_{selected_fy.fy_no}_{window.date_from}_{window.date_to}_{status_filter}"
        return gstr1_export_http_response(
            report_rows=report_rows,
            export_fmt=export_fmt,
            filename_base=fn,
        )

    return render(
        request,
        "invoices/reports_gstr1_invoice_list.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "report_submitted": submitted,
            "status_filter": status_filter,
            "month_options": month_options,
            "selected_month_value": selected_month_value,
            "ytd": ytd,
            "window": window,
            "report_rows": report_rows,
        },
    )


@login_required
def receipts_home(request):
    _require_setup_module(request)
    return render(request, "invoices/receipts.html")
def _latest_invoice_fy() -> FiscalYear | None:
    latest_inv = Invoice.objects.order_by("-invoice_date", "-id").first()
    if latest_inv is None:
        return None
    return _fiscal_year_containing_date(latest_inv.invoice_date)


@login_required
def invoice_list(request):
    _require_setup_module(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            inv = get_object_or_404(Invoice, pk=request.POST.get("pk"))
            if inv.posted_gl_header_id:
                messages.error(
                    request,
                    "This invoice is posted to the general ledger and cannot be deleted.",
                )
                return redirect("invoices")
            udin_pks = set(inv.inv_udin_maps.values_list("udin_id", flat=True))
            inv.delete()
            sync_udin_flags_for_pks(udin_pks)
            return redirect("invoices")
        if action == "bulk_authorize":
            ids = request.POST.getlist("invoice_id")
            n, errs = bulk_post_fresh_invoices_to_gl(invoice_pks=ids, user=request.user)
            if n:
                messages.success(
                    request,
                    f"Posted {n} invoice(s) to the GL and marked them Authorised.",
                )
            for e in errs:
                messages.error(request, e)
            next_status = (request.POST.get("next_status") or "fresh").strip().lower()
            if next_status not in ("all", "fresh", "authorised"):
                next_status = "fresh"
            q = urlencode({"status": next_status}) if next_status != "fresh" else ""
            url = reverse("invoices")
            return redirect(f"{url}?{q}" if q else url)
        return redirect("invoices")

    status_filter = (request.GET.get("status") or "fresh").strip().lower()
    if status_filter not in ("all", "fresh", "authorised"):
        status_filter = "fresh"

    fiscal_years = list(FiscalYear.objects.all())
    fy_param = request.GET.get("fy")
    if fy_param == "all":
        selected_fy = None
    elif fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
        if selected_fy is None:
            selected_fy = _latest_invoice_fy() or (fiscal_years[0] if fiscal_years else None)
    else:
        selected_fy = _latest_invoice_fy() or (fiscal_years[0] if fiscal_years else None)


    inv_qs = Invoice.objects.select_related(
        "client", "service", "fiscal_year", "created_by", "posted_gl_header"
    ).prefetch_related(
        Prefetch(
            "inv_udin_maps",
            queryset=InvUdinMap.objects.select_related("udin").order_by("line_no"),
        )
    )
    if status_filter == "fresh":
        inv_qs = inv_qs.filter(status=InvoiceStatus.FRESH)
    elif status_filter == "authorised":
        inv_qs = inv_qs.filter(status=InvoiceStatus.AUTHORISED)
    if selected_fy is not None:
        inv_qs = inv_qs.filter(
            invoice_date__gte=selected_fy.start_date,
            invoice_date__lte=selected_fy.end_date,
        )
    invoices = inv_qs.order_by("-invoice_date", "-id")

    totals = invoices.aggregate(
        total_tv=Sum("inv_taxable_value"),
        total_taxes=Sum("taxes"),
        total_gross=Sum("inv_gross"),
    )

    return render(
        request,
        "invoices/invoices.html",
        {
            "invoices": invoices,
            "status_filter": status_filter,
            "fiscal_years": fiscal_years,
            "selected_fy": selected_fy,
            "totals": totals,
        },
    )



@login_required
def invoice_create(request):
    _require_setup_module(request)
    return _invoice_form_view(request)


@login_required
def invoice_edit(request, pk: int):
    _require_setup_module(request)
    inv = get_object_or_404(Invoice, pk=pk)
    return _invoice_form_view(request, instance=inv)


def _invoice_form_view(request, instance=None):
    invoice_pk = instance.pk if instance else None
    udin_qs = udin_choice_queryset_for_invoice(invoice_pk=invoice_pk)
    udin_choice_meta = _udin_choice_meta(udin_qs)

    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=instance)
        formset = _map_formset_for_request(data=request.POST, instance=instance)
        if form.is_valid() and formset.is_valid():
            rows = formset._cleaned_map_rows
            first_client = rows[0][0].client
            duplicate_no = Invoice.objects.filter(
                client=first_client,
                invoice_no=form.cleaned_data["invoice_no"],
            )
            if instance is not None:
                duplicate_no = duplicate_no.exclude(pk=instance.pk)
            if duplicate_no.exists():
                form.add_error(
                    "invoice_no",
                    f"Invoice no {form.cleaned_data['invoice_no']} already exists "
                    f"for {first_client.client_short_name}.",
                )
        if form.is_valid() and formset.is_valid():
            rows = formset._cleaned_map_rows
            tax_type = rows[0][0].client.invoice_tax_type
            entries = [{"line_amount": r[2], "service_desc": r[1]} for r in rows]
            lines = build_invoice_lines_from_map_entries(
                map_entries=entries,
                invoice_tax_type=tax_type,
            )
            tv = money2(sum(r[2] for r in rows))
            tax_tot = taxes_total_from_lines(lines)
            gross = gross_from_lines(lines, tv)
            old_udin_pks = set()
            if instance:
                old_udin_pks = set(instance.inv_udin_maps.values_list("udin_id", flat=True))
            with transaction.atomic():
                inv = form.save(commit=False)
                first_udin = rows[0][0]
                inv.client = first_udin.client
                inv.service = first_udin.service
                inv.inv_taxable_value = tv
                inv.taxes = tax_tot
                inv.inv_gross = gross
                if instance is None:
                    inv.created_by = request.user
                inv.save()
                persist_maps_and_lines(invoice=inv, map_rows=rows, invoice_tax_type=tax_type)
            new_udin_pks = {r[0].pk for r in rows}
            sync_udin_flags_for_pks(old_udin_pks | new_udin_pks, invoice=inv)
            if getattr(formset, "_duplicate_udin", False):
                messages.warning(
                    request,
                    "The same UDIN appears more than once on this invoice. Confirm that is intentional.",
                )
            return redirect("invoice_preview", pk=inv.pk)
        prev_nav, next_nav = _invoice_nav_neighbors(instance)
        return render(
            request,
            "invoices/invoice_form.html",
            {
                "form": form,
                "map_formset": formset,
                "invoice": instance,
                "udin_choice_meta": udin_choice_meta,
                "is_invoice_create": instance is None,
                "invoice_nav_prev": prev_nav,
                "invoice_nav_next": next_nav,
            },
        )

    form = InvoiceForm(instance=instance)
    formset = _map_formset_for_request(data=None, instance=instance)
    prev_nav, next_nav = _invoice_nav_neighbors(instance)
    return render(
        request,
        "invoices/invoice_form.html",
        {
            "form": form,
            "map_formset": formset,
            "invoice": instance,
            "udin_choice_meta": udin_choice_meta,
            "is_invoice_create": instance is None,
            "invoice_nav_prev": prev_nav,
            "invoice_nav_next": next_nav,
        },
    )


@login_required
@require_GET
def invoice_preview(request, pk: int):
    _require_setup_module(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "service", "fiscal_year", "created_by")
        .prefetch_related(
            Prefetch(
                "inv_udin_maps",
                queryset=InvUdinMap.objects.select_related("udin").order_by("line_no"),
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "invoices/invoice_preview.html",
        build_invoice_preview_context(request, inv),
    )


@login_required
@require_GET
def invoice_next_no(request):
    _require_setup_module(request)
    raw_cid = (request.GET.get("client_id") or "").strip()
    raw_date = (request.GET.get("invoice_date") or "").strip()
    if not raw_cid.isdigit() or not raw_date:
        return JsonResponse({"invoice_no": ""}, status=400)
    try:
        inv_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"invoice_no": ""}, status=400)
    client = Client.objects.filter(pk=int(raw_cid)).first()
    if not client:
        return JsonResponse({"invoice_no": ""}, status=404)
    suggested = next_invoice_no(client=client, invoice_date=inv_date)
    return JsonResponse({"invoice_no": suggested})
