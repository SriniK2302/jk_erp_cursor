"""UDIN Source staging workflow — Source, UDINs, and Invoices are three separate registers."""

from __future__ import annotations

from django.utils import timezone

from .models import UdinSource


def mark_source_row_copied_to_udins(source: UdinSource) -> None:
    """Record that this source row has been copied onto the UDINs register (source row is kept)."""
    source.copied_to_udins = True
    source.copied_on = timezone.now()
    source.save(update_fields=["copied_to_udins", "copied_on", "updated_on"])
