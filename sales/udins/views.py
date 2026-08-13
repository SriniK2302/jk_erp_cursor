import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Func, Prefetch, Value
from django.db.models.functions import NullIf
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from sales.clients.models import Client
from sales.services.models import Service
from sales.udins_source.models import UdinSource
from sales.udins_source.workflow import mark_source_row_copied_to_udins

from sales.udins.udin_no import normalize_udin
from sales.udins.service_remarks_build import (
    bulk_fill_client_from_remarks,
    derive_service_remarks,
    explain_service_remarks_failure,
    service_remarks_is_blank,
)
from sales.udins.service_fy_build import derive_service_fy

from .forms import (
    CertificationFeeRateForm,
    UdinClientBulkUpdateForm,
    UdinForm,
    UdinInvTvBulkUpdateForm,
    UdinServiceBulkUpdateForm,
)
from sales.invoices.invoice_from_udin import (
    create_invoice_from_udin,
    inv_tv_amount_from_form_value,
    invoice_readiness_issues,
)
from sales.invoices.models import InvUdinMap, Invoice
from sales.invoices.bulk_pdf_zip import save_bulk_invoice_zip
from sales.invoices.pdf_export import PdfExportError, invoice_html_list_to_pdf_bytes
from sales.invoices.permissions import require_setup_module
from sales.invoices.preview_context import build_invoice_preview_context

from .models import CertificationFeeRate, CertificationPeriodFee, Udin
from .certification_period_fee import (
    bulk_apply_certification_period_fees_to_udins,
    maybe_apply_certification_period_fee,
)

_UDINS_INVOICE_STATUS_SESSION_KEY = "udins_invoice_status"
_BULK_INVOICE_ZIP_SESSION_KEY = "bulk_invoice_zip_relpath"


def _normalize_status(value: str) -> str:
    text = (value or "").strip().lower()
    if text == "active":
        return "Active"
    if text == "revoked":
        return "Revoked"
    return ""


def _parse_create_date(raw: str):
    text = (raw or "").strip()
    if not text:
        return None
    date_part = text.split("|", 1)[0].strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue
    return None


@login_required
def udins(request):
    invoice_status = "pending"
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        invoice_status = (request.POST.get("invoice_status") or "").strip().lower()
        if invoice_status not in {"all", "invoiced", "pending"}:
            invoice_status = request.session.get(_UDINS_INVOICE_STATUS_SESSION_KEY, "pending")
            if invoice_status not in {"all", "invoiced", "pending"}:
                invoice_status = "pending"
        request.session[_UDINS_INVOICE_STATUS_SESSION_KEY] = invoice_status

        if action == "delete":
            row = get_object_or_404(Udin, pk=request.POST.get("pk"))
            row.delete()
            messages.success(request, "UDIN deleted.")
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "import_from_source":
            imported = 0
            updated = 0
            copied = 0
            with transaction.atomic():
                for source in list(UdinSource.objects.filter(copied_to_udins=False)):
                    udin_no = normalize_udin(source.udin)
                    if not udin_no:
                        source.delete()
                        continue
                    if source.udin != udin_no:
                        source.udin = udin_no
                        source.save(update_fields=["udin", "updated_on"])
                    row, created = Udin.objects.get_or_create(
                        udin=udin_no,
                        defaults={"created_by": request.user},
                    )
                    row.remarks = source.remarks
                    row.date_of_signing_of_document = source.date_of_signing_of_document
                    row.ay_fy = source.ay_fy or ""
                    row.create_date = _parse_create_date(source.created_date_time)
                    row.created_date_time = source.created_date_time
                    row.status = _normalize_status(source.status)
                    row.is_manual = False
                    row.save(
                        update_fields=[
                            "remarks",
                            "date_of_signing_of_document",
                            "ay_fy",
                            "create_date",
                            "created_date_time",
                            "status",
                            "is_manual",
                            "updated_on",
                        ]
                    )
                    mark_source_row_copied_to_udins(source)
                    copied += 1
                    if created:
                        imported += 1
                    else:
                        updated += 1
            messages.success(
                request,
                f"Copied {copied} row(s) from UDIN Source onto the UDINs register "
                f"(imported {imported} new, updated {updated} existing). Source rows are unchanged.",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_fill_client_from_remarks":
            updated, skipped = bulk_fill_client_from_remarks()
            messages.success(
                request,
                f"Client set on {updated} UDIN row(s) from client code in Remarks. "
                f"Skipped {skipped} row(s) (no matching code or client already set).",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_update_client_by_remarks_prefix":
            bulk_form = UdinClientBulkUpdateForm(request.POST)
            if bulk_form.is_valid():
                prefix = bulk_form.cleaned_data["prefix"]
                client = bulk_form.cleaned_data["client"]
                updated = Udin.objects.filter(
                    client__isnull=True,
                    remarks__icontains=prefix,
                ).update(client=client)
                messages.success(request, f"Client updated for {updated} UDIN rows by text match.")
            else:
                for field_errors in bulk_form.errors.values():
                    for err in field_errors:
                        messages.error(request, err)
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_update_service_by_remarks_prefix":
            bulk_form = UdinServiceBulkUpdateForm(request.POST)
            if bulk_form.is_valid():
                prefix = bulk_form.cleaned_data["prefix"]
                service = bulk_form.cleaned_data["service"]
                updated = Udin.objects.filter(
                    service__isnull=True,
                    remarks__icontains=prefix,
                ).update(service=service)
                messages.success(request, f"Service updated for {updated} UDIN rows by text match.")
            else:
                for field_errors in bulk_form.errors.values():
                    for err in field_errors:
                        messages.error(request, err)
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_update_inv_tv_by_client_service":
            bulk_form = UdinInvTvBulkUpdateForm(request.POST)
            if bulk_form.is_valid():
                client = bulk_form.cleaned_data["client"]
                service = bulk_form.cleaned_data["service"]
                fee = bulk_form.cleaned_data["fee_amount"]
                updated = Udin.objects.filter(
                    client=client,
                    service=service,
                    inv_tv_amount__isnull=True,
                ).update(inv_tv_amount=fee)
                messages.success(
                    request,
                    f"Inv TV amt set for {updated} UDIN row(s) with this client and service (blank amounts only).",
                )
            else:
                for field_errors in bulk_form.errors.values():
                    for err in field_errors:
                        messages.error(request, err)
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_fill_service_remarks_certification":
            updated = 0
            skipped = 0
            rows_qs = Udin.objects.select_related("client", "service")
            if invoice_status == "invoiced":
                rows_qs = rows_qs.filter(is_invoiced=True)
            elif invoice_status == "pending":
                rows_qs = rows_qs.filter(is_invoiced=False)
            with transaction.atomic():
                for row in rows_qs:
                    if not service_remarks_is_blank(row.service_remarks):
                        skipped += 1
                        continue
                    derived = derive_service_remarks(
                        remarks=row.remarks,
                        client=row.client,
                        service=row.service,
                    )
                    if not derived:
                        skipped += 1
                        continue
                    if row.service_remarks != derived:
                        row.service_remarks = derived
                        row.save(update_fields=["service_remarks", "updated_on"])
                        updated += 1
            messages.success(
                request,
                f"Filled service remarks on {updated} Certification UDIN row(s). "
                f"Skipped {skipped} row(s) (not Certification, missing client/remarks, or service remarks already set).",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_fill_service_fy":
            updated = 0
            skipped = 0
            rows_qs = Udin.objects.select_related("service")
            if invoice_status == "invoiced":
                rows_qs = rows_qs.filter(is_invoiced=True)
            elif invoice_status == "pending":
                rows_qs = rows_qs.filter(is_invoiced=False)
            with transaction.atomic():
                for row in rows_qs:
                    derived = derive_service_fy(
                        service=row.service,
                        date_of_signing_of_document=row.date_of_signing_of_document,
                        remarks=row.remarks,
                        ay_fy=row.ay_fy,
                    )
                    if not derived:
                        skipped += 1
                        continue
                    if row.ay_fy != derived:
                        row.ay_fy = derived
                        row.save(update_fields=["ay_fy", "updated_on"])
                        updated += 1
            messages.success(
                request,
                f"Filled Service FY on {updated} UDIN row(s). "
                f"Skipped {skipped} row(s) (unsupported service or missing date/remarks).",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_apply_certification_fees":
            updated, skipped = bulk_apply_certification_period_fees_to_udins(only_blank=True)
            messages.success(
                request,
                f"Set Inv TV amt on {updated} Certification UDIN row(s) from client fee periods. "
                f"Skipped {skipped} row(s) (not Certification, Inv TV already set, or no matching fee). "
                f"Applied across all UDINs, not only the current list filter.",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        if action == "bulk_generate_invoices":
            try:
                require_setup_module(request)
            except PermissionDenied as exc:
                messages.error(request, str(exc))
                return redirect(f"{request.path}?invoice_status={invoice_status}")
            raw_ids = request.POST.getlist("udin_ids")
            pks: list[int] = []
            for x in raw_ids:
                s = str(x).strip()
                if s.isdigit():
                    pks.append(int(s))
            if not pks:
                messages.warning(request, "Select at least one UDIN to generate invoices.")
                return redirect(f"{request.path}?invoice_status={invoice_status}")
            created: list = []
            for pk in pks:
                udin = Udin.objects.filter(pk=pk).select_related("client", "service").first()
                if not udin:
                    messages.error(request, f"UDIN id {pk} not found; skipped.")
                    continue
                inv, err = create_invoice_from_udin(user=request.user, udin=udin)
                if err:
                    messages.error(request, f"{udin.udin}: {err}")
                else:
                    created.append(inv)
            if not created:
                messages.warning(request, "No invoices were created.")
                return redirect(f"{request.path}?invoice_status={invoice_status}")
            html_docs: list[str] = []
            safe_names: list[str] = []
            for inv in created:
                inv_full = (
                    Invoice.objects.filter(pk=inv.pk)
                    .select_related("client", "service", "fiscal_year", "created_by")
                    .prefetch_related(
                        Prefetch(
                            "inv_udin_maps",
                            queryset=InvUdinMap.objects.select_related("udin").order_by(
                                "line_no"
                            ),
                        )
                    )
                    .first()
                )
                if not inv_full:
                    continue
                ctx = build_invoice_preview_context(request, inv_full)
                html_docs.append(
                    render_to_string(
                        "invoices/invoice_preview.html", ctx, request=request
                    )
                )
                safe_names.append(
                    re.sub(r"[^\w.\-]+", "_", inv_full.invoice_no) or f"inv_{inv_full.pk}"
                )
            try:
                pdf_parts = invoice_html_list_to_pdf_bytes(html_documents=html_docs)
            except PdfExportError as exc:
                messages.error(
                    request,
                    "Invoices were created, but PDF export failed: "
                    + str(exc)
                    + " You can still open each invoice from the Invoices list and use Print / Save as PDF.",
                )
                return redirect("invoices")
            if len(pdf_parts) != len(safe_names):
                messages.error(
                    request,
                    "Invoices were created, but PDF export returned an unexpected result. "
                    "Open each invoice from the Invoices list and use Print / Save as PDF.",
                )
                return redirect("invoices")
            rel_path, abs_path = save_bulk_invoice_zip(pdf_parts=pdf_parts, safe_names=safe_names)
            request.session[_BULK_INVOICE_ZIP_SESSION_KEY] = rel_path
            messages.success(
                request,
                f"Created {len(created)} invoice(s). PDF ZIP saved — use Download invoice PDFs (ZIP) below "
                f"({abs_path}).",
            )
            return redirect(f"{request.path}?invoice_status={invoice_status}")
        return redirect(f"{request.path}?invoice_status={invoice_status}")

    raw_get = request.GET.get("invoice_status")
    if raw_get is not None and str(raw_get).strip() != "":
        parsed = str(raw_get).strip().lower()
        if parsed in {"all", "invoiced", "pending"}:
            invoice_status = parsed
            request.session[_UDINS_INVOICE_STATUS_SESSION_KEY] = invoice_status
        else:
            invoice_status = request.session.get(_UDINS_INVOICE_STATUS_SESSION_KEY, "pending")
            if invoice_status not in {"all", "invoiced", "pending"}:
                invoice_status = "pending"
    else:
        invoice_status = request.session.get(_UDINS_INVOICE_STATUS_SESSION_KEY, "pending")
        if invoice_status not in {"all", "invoiced", "pending"}:
            invoice_status = "pending"

    rows_qs = Udin.objects.select_related("created_by", "source_row", "client", "service")
    if invoice_status == "invoiced":
        rows_qs = rows_qs.filter(is_invoiced=True)
    elif invoice_status == "pending":
        rows_qs = rows_qs.filter(is_invoiced=False)
    rows = (
        rows_qs.annotate(
            signed_doc_date_sort=Func(
                NullIf(F("date_of_signing_of_document"), Value("")),
                Value("DD-MM-YYYY"),
                function="TO_DATE",
            )
        )
        .order_by(F("signed_doc_date_sort").asc(nulls_last=True), "id")
        .all()
    )
    bulk_client_form = UdinClientBulkUpdateForm()
    bulk_service_form = UdinServiceBulkUpdateForm()
    bulk_inv_tv_form = UdinInvTvBulkUpdateForm()
    bulk_zip_download_url = None
    if request.session.get(_BULK_INVOICE_ZIP_SESSION_KEY):
        from django.urls import reverse

        bulk_zip_download_url = reverse("bulk_invoice_zip_download")
    return render(
        request,
        "udins/udins.html",
        {
            "rows": rows,
            "invoice_status": invoice_status,
            "bulk_client_form": bulk_client_form,
            "bulk_service_form": bulk_service_form,
            "bulk_inv_tv_form": bulk_inv_tv_form,
            "bulk_zip_download_url": bulk_zip_download_url,
        },
    )


def _bulk_invoice_zip_path(request) -> Path | None:
    rel = (request.session.get(_BULK_INVOICE_ZIP_SESSION_KEY) or "").strip()
    if not rel or ".." in rel.replace("\\", "/"):
        return None
    media_root = Path(settings.MEDIA_ROOT).resolve()
    path = (media_root / rel).resolve()
    if not str(path).startswith(str(media_root)) or not path.is_file():
        return None
    return path


@login_required
def bulk_invoice_zip_download(request):
    try:
        require_setup_module(request)
    except PermissionDenied as exc:
        messages.error(request, str(exc))
        return redirect("udins")
    path = _bulk_invoice_zip_path(request)
    if path is None:
        request.session.pop(_BULK_INVOICE_ZIP_SESSION_KEY, None)
        messages.error(request, "No bulk invoice ZIP is available. Generate again from UDINs.")
        return redirect("udins")
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=path.name,
        content_type="application/zip",
    )


def _post_int(raw) -> int | None:
    text = str(raw or "").strip()
    return int(text) if text.isdigit() else None


def _client_from_post(post) -> Client | None:
    pk = _post_int(post.get("client"))
    if pk is None:
        return None
    return Client.objects.filter(pk=pk).first()


def _service_from_post(post) -> Service | None:
    pk = _post_int(post.get("service"))
    if pk is None:
        return None
    return Service.objects.filter(pk=pk).first()


def _parse_form_date(raw: str):
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _merge_udin_post_onto_instance(instance, post, *, extra_updates: dict | None = None) -> list[str]:
    """Apply billing-prep POST values; blank client/service keeps existing DB values."""
    update_fields: list[str] = []
    extra_updates = extra_updates or {}

    for attr, value in extra_updates.items():
        setattr(instance, attr, value)
        update_fields.append(attr)

    client_pk = _post_int(post.get("client"))
    if client_pk is not None:
        instance.client_id = client_pk
        update_fields.append("client")

    service_pk = _post_int(post.get("service"))
    if service_pk is not None:
        instance.service_id = service_pk
        update_fields.append("service")

    skip_text = set(extra_updates)
    for text_attr in (
        "remarks",
        "date_of_signing_of_document",
        "service_remarks",
        "status",
        "inv_no",
    ):
        if text_attr in skip_text or text_attr not in post:
            continue
        value = post.get(text_attr) or ""
        if text_attr == "service_remarks" and not str(value).strip():
            continue
        if getattr(instance, text_attr) != value:
            setattr(instance, text_attr, value)
            update_fields.append(text_attr)

    create_date = _parse_form_date(post.get("create_date") or "")
    if create_date is not None and instance.create_date != create_date:
        instance.create_date = create_date
        update_fields.append("create_date")

    inv_date = _parse_form_date(post.get("inv_date") or "")
    if inv_date is not None and instance.inv_date != inv_date:
        instance.inv_date = inv_date
        update_fields.append("inv_date")

    inv_tv = inv_tv_amount_from_form_value(post.get("inv_tv_amount"))
    if inv_tv is not None and instance.inv_tv_amount != inv_tv:
        instance.inv_tv_amount = inv_tv
        update_fields.append("inv_tv_amount")

    return update_fields


def _post_with_instance_service_remarks(post, instance):
    """Keep saved service remarks visible when billing-prep POST omits or clears the field."""
    post = post.copy()
    if instance is not None and service_remarks_is_blank(post.get("service_remarks")):
        if not service_remarks_is_blank(instance.service_remarks):
            post["service_remarks"] = instance.service_remarks
    return post


def _udin_form_from_post(post, instance=None):
    return UdinForm(_post_with_instance_service_remarks(post, instance), instance=instance)


def _render_udin_form(request, *, form, instance=None, invoice_ready_result=None, billing_prep_feedback=None):
    return render(
        request,
        "udins/udin_form.html",
        {
            "form": form,
            "row": instance,
            "invoice_ready_result": invoice_ready_result,
            "billing_prep_feedback": billing_prep_feedback,
        },
    )


def _save_udin_from_form(form, *, request, instance):
    row = form.save(commit=False)
    if instance is None:
        row.created_by = request.user
        row.is_manual = True
    row.save()
    maybe_apply_certification_period_fee(row, save=True)
    return row


def _udin_form_view(request, instance=None):
    if request.method == "POST":
        post = request.POST.copy()

        if request.POST.get("check_invoice_ready"):
            form = _udin_form_from_post(post, instance)
            issues = invoice_readiness_issues(
                client_id=_post_int(post.get("client")),
                service_id=_post_int(post.get("service")),
                ay_fy=post.get("ay_fy") or "",
                inv_tv_amount=inv_tv_amount_from_form_value(post.get("inv_tv_amount")),
                is_invoiced=bool(instance and instance.is_invoiced),
                udin_pk=instance.pk if instance else None,
            )
            invoice_ready_result = {"ready": not issues, "issues": issues}
            if issues:
                messages.warning(request, "This UDIN is not ready for invoice yet.")
            else:
                messages.success(request, "This UDIN is ready for invoice.")
            return _render_udin_form(
                request,
                form=form,
                instance=instance,
                invoice_ready_result=invoice_ready_result,
            )

        if request.POST.get("derive_service_remarks"):
            if not service_remarks_is_blank(post.get("service_remarks")):
                messages.info(request, "Service remarks already set; not updated.")
                return _render_udin_form(
                    request,
                    form=_udin_form_from_post(post, instance),
                    instance=instance,
                    billing_prep_feedback={
                        "level": "info",
                        "text": "Service remarks already set; not updated.",
                    },
                )
            remarks = (post.get("remarks") or "").strip()
            if not remarks and instance is not None:
                remarks = (instance.remarks or "").strip()
            client = _client_from_post(post) or (
                instance.client if instance and instance.client_id else None
            )
            service = _service_from_post(post) or (
                instance.service if instance and instance.service_id else None
            )
            derived = derive_service_remarks(
                remarks=remarks,
                client=client,
                service=service,
            )
            if not derived:
                feedback = explain_service_remarks_failure(
                    remarks=remarks,
                    client=client,
                    service=service,
                )
                messages.warning(request, feedback)
                return _render_udin_form(
                    request,
                    form=_udin_form_from_post(post, instance),
                    instance=instance,
                    billing_prep_feedback={"level": "warn", "text": feedback},
                )
            if instance is not None:
                update_fields = _merge_udin_post_onto_instance(
                    instance,
                    post,
                    extra_updates={"service_remarks": derived},
                )
                if update_fields:
                    update_fields = list(dict.fromkeys(update_fields + ["updated_on"]))
                    instance.save(update_fields=update_fields)
                instance.refresh_from_db()
                messages.success(request, f"Service remarks updated: {derived}.")
                return _render_udin_form(
                    request,
                    form=UdinForm(instance=instance),
                    instance=instance,
                    billing_prep_feedback={
                        "level": "ok",
                        "text": f"Service remarks updated: {derived}",
                    },
                )
            post["service_remarks"] = derived
            return _render_udin_form(
                request,
                form=UdinForm(post, instance=instance),
                instance=instance,
                billing_prep_feedback={
                    "level": "ok",
                    "text": f"Service remarks set to: {derived}. Save UDIN to keep.",
                },
            )

        if request.POST.get("derive_service_fy"):
            service = _service_from_post(post)
            derived = derive_service_fy(
                service=service,
                date_of_signing_of_document=post.get("date_of_signing_of_document") or "",
                remarks=post.get("remarks") or "",
                ay_fy=post.get("ay_fy") or "",
            )
            if not derived:
                messages.warning(
                    request,
                    "Could not update Service FY. For Certification set document date; "
                    "for Audit set Service and use Remarks (e.g. FY26 or YE 31.3.2026).",
                )
                return _render_udin_form(request, form=_udin_form_from_post(post, instance), instance=instance)
            if instance is not None:
                update_fields = _merge_udin_post_onto_instance(
                    instance,
                    post,
                    extra_updates={"ay_fy": derived},
                )
                if update_fields:
                    update_fields = list(dict.fromkeys(update_fields + ["updated_on"]))
                    instance.save(update_fields=update_fields)
                messages.success(request, f"Service FY updated: {derived}.")
                return redirect("udin_edit", pk=instance.pk)
            post["ay_fy"] = derived
            return _render_udin_form(request, form=_udin_form_from_post(post, instance), instance=instance)

        form = UdinForm(request.POST, instance=instance)
        if form.is_valid():
            _save_udin_from_form(form, request=request, instance=instance)
            return redirect("udins")
    else:
        form = UdinForm(instance=instance)
    return _render_udin_form(request, form=form, instance=instance)


@login_required
def udin_create(request):
    return _udin_form_view(request)


@login_required
def udin_edit(request, pk):
    row = get_object_or_404(Udin, pk=pk)
    return _udin_form_view(request, instance=row)


@login_required
def certification_fee_rates(request):
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "delete":
            row = get_object_or_404(CertificationFeeRate, pk=request.POST.get("pk"))
            row.delete()
            messages.success(request, "Certification fee rate deleted.")
            return redirect("certification_fee_rates")
        if action == "apply_all_to_udins":
            updated_rows = 0
            with transaction.atomic():
                for rate in CertificationFeeRate.objects.select_related("client", "service"):
                    n = Udin.objects.filter(
                        client_id=rate.client_id,
                        service_id=rate.service_id,
                        inv_tv_amount__isnull=True,
                    ).update(inv_tv_amount=rate.fee_amount)
                    updated_rows += n
            messages.success(
                request,
                f"Applied certification fee rates where Inv TV amt was unset. UDIN rows updated: {updated_rows}.",
            )
            return redirect("certification_fee_rates")
        return redirect("certification_fee_rates")

    rates = CertificationFeeRate.objects.select_related("client", "service").all()
    return render(
        request,
        "udins/certification_fee_rates.html",
        {"rates": rates},
    )


def _certification_fee_rate_form_view(request, instance=None):
    if request.method == "POST":
        form = CertificationFeeRateForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("certification_fee_rates")
    else:
        form = CertificationFeeRateForm(instance=instance)
    return render(
        request,
        "udins/certification_fee_rate_form.html",
        {"form": form, "row": instance},
    )


@login_required
def certification_fee_rate_create(request):
    return _certification_fee_rate_form_view(request)


@login_required
def certification_fee_rate_edit(request, pk):
    row = get_object_or_404(CertificationFeeRate, pk=pk)
    return _certification_fee_rate_form_view(request, instance=row)
