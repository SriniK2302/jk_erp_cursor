"""Certification fee by client and date period for UDIN Inv TV amt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import CertificationPeriodFee, Udin
from .service_fy_build import parse_udin_document_date
from .service_rules import is_certification_service


def certification_period_fee_lookup(
    *,
    client_id: int | None,
    signing_date: date | None,
) -> Decimal | None:
    if not client_id or signing_date is None:
        return None
    row = (
        CertificationPeriodFee.objects.filter(
            client_id=client_id,
            from_date__lte=signing_date,
            to_date__gte=signing_date,
        )
        .order_by("-from_date", "-id")
        .first()
    )
    if row is None:
        return None
    return row.fee_amount


def certification_period_fee_for_udin(udin: Udin) -> Decimal | None:
    if not udin.client_id:
        return None
    if not is_certification_service(udin.service):
        return None
    doc_date = parse_udin_document_date(udin.date_of_signing_of_document or "")
    return certification_period_fee_lookup(client_id=udin.client_id, signing_date=doc_date)


def maybe_apply_certification_period_fee(udin: Udin, *, save: bool = False) -> bool:
    if udin.inv_tv_amount is not None:
        return False
    fee = certification_period_fee_for_udin(udin)
    if fee is None:
        return False
    udin.inv_tv_amount = fee
    if save and udin.pk:
        udin.save(update_fields=["inv_tv_amount", "updated_on"])
    return True


def bulk_apply_certification_period_fees_to_udins(
    *,
    only_blank: bool = True,
    client_id: int | None = None,
) -> tuple[int, int]:
    """
    Apply client fee periods to all matching Certification UDINs in one pass.
    Returns (updated_count, skipped_count).
    """
    qs = Udin.objects.filter(client_id__isnull=False).select_related("service", "client")
    if only_blank:
        qs = qs.filter(inv_tv_amount__isnull=True)
    if client_id is not None:
        qs = qs.filter(client_id=client_id)
    updated = 0
    skipped = 0
    with transaction.atomic():
        for udin in qs.iterator():
            if not is_certification_service(udin.service):
                skipped += 1
                continue
            if maybe_apply_certification_period_fee(udin, save=True):
                updated += 1
            else:
                skipped += 1
    return updated, skipped
