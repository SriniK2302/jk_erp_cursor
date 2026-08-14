"""
Find missing files across the legacy attachment tables and report them with
business-meaningful context (Client, Fiscal Year, Service, Division/Work Area)
instead of internal folder codes.

This only reads and reports -- it does not change any data.

Usage:
    python manage.py report_missing_work_documents
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand

from engagements.models import (
    DivisionWorkAreaDocument,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDocumentationMapAttachment,
)


def _missing(file_field) -> bool:
    if not file_field:
        return False
    try:
        return not os.path.exists(file_field.path)
    except (ValueError, NotImplementedError):
        return False


class Command(BaseCommand):
    help = "Report missing files with business context (Client / FY / Service)."

    def handle(self, *args, **options):
        found_any = False

        self.stdout.write("=== Division Work Area Documents ===")
        for row in DivisionWorkAreaDocument.objects.select_related(
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
        ):
            if not _missing(row.file):
                continue
            found_any = True
            eng = row.work_area.division.engagement
            self.stdout.write(
                f"  id={row.pk} | Client: {eng.client.client_name} | "
                f"FY: {eng.fiscal_year.fy_no} | Service: {eng.service.service_desc} | "
                f"Division: {row.work_area.division.division_name} | "
                f"Work area: {row.work_area.work_area_name} | "
                f"Description: {row.description or '(none)'} | "
                f"Original filename: {row.original_filename}"
            )

        self.stdout.write("")
        self.stdout.write("=== Engagement Documentation Map Attachments ===")
        for row in EngagementDocumentationMapAttachment.objects.select_related(
            "documentation_map__engagement__client",
            "documentation_map__engagement__fiscal_year",
            "documentation_map__engagement__service",
            "documentation_map__documentation",
        ):
            if not _missing(row.file):
                continue
            found_any = True
            eng = row.documentation_map.engagement
            doc = row.documentation_map.documentation
            self.stdout.write(
                f"  id={row.pk} | Client: {eng.client.client_name} | "
                f"FY: {eng.fiscal_year.fy_no} | Service: {eng.service.service_desc} | "
                f"Standard document: {doc.standard_document} | "
                f"Description: {row.description or '(none)'} | "
                f"Original filename: {row.original_filename}"
            )

        self.stdout.write("")
        self.stdout.write("=== Engagement Division Documentation Map Attachments ===")
        for row in EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division__engagement__client",
            "documentation_map__division__engagement__fiscal_year",
            "documentation_map__division__engagement__service",
            "documentation_map__documentation",
        ):
            if not _missing(row.file):
                continue
            found_any = True
            division = row.documentation_map.division
            eng = division.engagement
            doc = row.documentation_map.documentation
            self.stdout.write(
                f"  id={row.pk} | Client: {eng.client.client_name} | "
                f"FY: {eng.fiscal_year.fy_no} | Service: {eng.service.service_desc} | "
                f"Division: {division.division_name} | "
                f"Standard document: {doc.standard_document} | "
                f"Description: {row.description or '(none)'} | "
                f"Original filename: {row.original_filename}"
            )

        if not found_any:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("No missing files found."))
