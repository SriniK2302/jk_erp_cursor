"""Run all per-row UDIN billing-prep steps in one pass, for a single row.

Combines what used to be five separate bulk buttons — Fill Client from
Remarks, Fill service remarks (Certification), Fill Service FY, Fill Inv TV
amt (Certification), plus a new Invoice Date default — into one action for
one row. Existing values are never overwritten; only blank/derivable fields
are filled, so a manual override always sticks.
"""

from __future__ import annotations

from datetime import timedelta

from .certification_period_fee import maybe_apply_certification_period_fee
from .service_fy_build import derive_service_fy, parse_udin_document_date
from sales.services.models import Service

from .certification_period_fee import maybe_apply_certification_period_fee
from .service_fy_build import derive_service_fy, parse_udin_document_date
from sales.services.models import Service

from .certification_period_fee import maybe_apply_certification_period_fee
from .service_fy_build import derive_service_fy, parse_udin_document_date
from .service_remarks_build import (
    derive_service_remarks,
    find_client_by_code_in_remarks,
    service_remarks_is_blank,
)

INV_DATE_DAYS_AFTER_DOC_DATE = 29


def prepare_udin_row(udin, *, save: bool = True) -> list[str]:
    """
    Auto-fill one UDIN row: Client, Service remarks, Service FY, Inv TV amt
    (Certification), and Invoice Date (doc date + 29 days).

    Returns a list of short human-readable change descriptions (empty if
    nothing changed). Caller may wrap in transaction.atomic() if desired.
    """
    changes: list[str] = []
    update_fields: list[str] = []

    if udin.client_id is None:
        matched = find_client_by_code_in_remarks(udin.remarks or "")
        if matched is not None:
            udin.client = matched
            update_fields.append("client")
            changes.append(
                f"Client set to {matched.client_short_name or matched.client_code}."
            )

    if udin.service_id is None and "audit" not in (udin.remarks or "").lower():
        cert_service = Service.objects.filter(service_desc__icontains="certification").first()
        if cert_service is not None:
            udin.service = cert_service
            update_fields.append("service")
            changes.append(f"Service set to {cert_service.service_desc}.")

    if service_remarks_is_blank(udin.service_remarks):
        derived_remarks = derive_service_remarks(
            remarks=udin.remarks or "",
            client=udin.client,
            service=udin.service,
        )
        if derived_remarks:
            udin.service_remarks = derived_remarks
            update_fields.append("service_remarks")
            changes.append("Service remarks filled.")

    derived_fy = derive_service_fy(
        service=udin.service,
        date_of_signing_of_document=udin.date_of_signing_of_document or "",
        remarks=udin.remarks or "",
        ay_fy=udin.ay_fy or "",
    )
    if derived_fy and udin.ay_fy != derived_fy:
        udin.ay_fy = derived_fy
        update_fields.append("ay_fy")
        changes.append(f"Service FY set to {derived_fy}.")

    if maybe_apply_certification_period_fee(udin, save=False):
        update_fields.append("inv_tv_amount")
        changes.append(f"Inv TV amt set to {udin.inv_tv_amount}.")

    if udin.inv_date is None:
        doc_date = parse_udin_document_date(udin.date_of_signing_of_document or "")
        if doc_date is not None:
            udin.inv_date = doc_date + timedelta(days=INV_DATE_DAYS_AFTER_DOC_DATE)
            update_fields.append("inv_date")
            changes.append(
                f"Invoice date set to {udin.inv_date:%d-%m-%Y} "
                f"({INV_DATE_DAYS_AFTER_DOC_DATE} days from doc date)."
            )

    if save and update_fields and udin.pk:
        udin.save(update_fields=list(dict.fromkeys(update_fields + ["updated_on"])))

    return changes

