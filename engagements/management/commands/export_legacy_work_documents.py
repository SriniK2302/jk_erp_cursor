"""
Back up every file currently in the 5 legacy attachment tables into one zip
file, organized by category, with a manifest (CSV) describing each file in
business terms (Client, FY, Service, Division, Description).

This only reads existing files -- nothing is changed, moved, or deleted.

Usage:
    python manage.py export_legacy_work_documents
    python manage.py export_legacy_work_documents --output-dir D:\\backups
"""
from __future__ import annotations

import csv
import io
import os
import zipfile
from datetime import datetime

from django.core.management.base import BaseCommand

from engagements.models import (
    AuditQueryAttachment,
    DivisionWorkAreaDocument,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDocumentationMapAttachment,
    EngagementWorkAreaDocument,
)


def _safe(text: str) -> str:
    text = (text or "").strip() or "unnamed"
    bad = '\\/:*?"<>|'
    for ch in bad:
        text = text.replace(ch, "_")
    return text[:80]


class Command(BaseCommand):
    help = "Back up all legacy work-document files into one zip with a manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=".",
            help="Folder to write the backup zip into (default: current folder).",
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = os.path.join(output_dir, f"work_documents_backup_{timestamp}.zip")

        manifest_rows = []
        copied = 0
        missing = 0

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            copied, missing = self._add_audit_query_attachments(zf, manifest_rows, copied, missing)
            copied, missing = self._add_engagement_work_area_documents(zf, manifest_rows, copied, missing)
            copied, missing = self._add_division_work_area_documents(zf, manifest_rows, copied, missing)
            copied, missing = self._add_engagement_documentation_map_attachments(zf, manifest_rows, copied, missing)
            copied, missing = self._add_division_documentation_map_attachments(zf, manifest_rows, copied, missing)

            manifest_buffer = io.StringIO()
            writer = csv.writer(manifest_buffer)
            writer.writerow([
                "Category", "Legacy ID", "Client", "Fiscal Year", "Service",
                "Division", "Work Area / Standard Document", "Description",
                "Original Filename", "Path In Zip", "Status",
            ])
            for row in manifest_rows:
                writer.writerow(row)
            zf.writestr("manifest.csv", manifest_buffer.getvalue())

        self.stdout.write(self.style.SUCCESS(f"Backup created: {zip_path}"))
        self.stdout.write(f"Files copied: {copied}")
        self.stdout.write(f"Files missing (recorded in manifest, not in zip): {missing}")

    def _write_file(self, zf, category, legacy_id, original_filename, file_field, manifest_extra):
        folder = f"{category}/{legacy_id}_{_safe(original_filename)}"
        try:
            file_field.open("rb")
            try:
                data = file_field.read()
            finally:
                file_field.close()
        except (FileNotFoundError, OSError):
            manifest_extra.extend([original_filename, "(missing)", "MISSING"])
            return False

        zf.writestr(folder, data)
        manifest_extra.extend([original_filename, folder, "OK"])
        return True

    def _add_audit_query_attachments(self, zf, manifest_rows, copied, missing):
        category = "audit_query_attachments"
        for row in AuditQueryAttachment.objects.select_related(
            "query__engagement_work_area__engagement__client",
            "query__engagement_work_area__engagement__fiscal_year",
            "query__engagement_work_area__engagement__service",
            "query__division_work_area__division__engagement__client",
            "query__division_work_area__division__engagement__fiscal_year",
            "query__division_work_area__division__engagement__service",
        ):
            query = row.query
            if query.engagement_work_area_id:
                eng = query.engagement_work_area.engagement
                division_name = ""
            else:
                eng = query.division_work_area.division.engagement
                division_name = query.division_work_area.division.division_name

            entry = [category, row.pk, eng.client.client_name, eng.fiscal_year.fy_no,
                     eng.service.service_desc, division_name, "Audit query attachment",
                     row.document_reference_no or ""]
            ok = self._write_file(zf, category, row.pk, row.original_filename, row.file, entry)
            manifest_rows.append(entry)
            copied += 1 if ok else 0
            missing += 0 if ok else 1

        self.stdout.write(f"  {category}: processed")
        return copied, missing

    def _add_engagement_work_area_documents(self, zf, manifest_rows, copied, missing):
        category = "engagement_work_area_documents"
        for row in EngagementWorkAreaDocument.objects.select_related(
            "work_area__engagement__client",
            "work_area__engagement__fiscal_year",
            "work_area__engagement__service",
        ):
            eng = row.work_area.engagement
            entry = [category, row.pk, eng.client.client_name, eng.fiscal_year.fy_no,
                     eng.service.service_desc, "", row.work_area.work_area_name,
                     row.description or ""]
            ok = self._write_file(zf, category, row.pk, row.original_filename, row.file, entry)
            manifest_rows.append(entry)
            copied += 1 if ok else 0
            missing += 0 if ok else 1

        self.stdout.write(f"  {category}: processed")
        return copied, missing

    def _add_division_work_area_documents(self, zf, manifest_rows, copied, missing):
        category = "division_work_area_documents"
        for row in DivisionWorkAreaDocument.objects.select_related(
            "work_area__division__engagement__client",
            "work_area__division__engagement__fiscal_year",
            "work_area__division__engagement__service",
        ):
            division = row.work_area.division
            eng = division.engagement
            entry = [category, row.pk, eng.client.client_name, eng.fiscal_year.fy_no,
                     eng.service.service_desc, division.division_name,
                     row.work_area.work_area_name, row.description or ""]
            ok = self._write_file(zf, category, row.pk, row.original_filename, row.file, entry)
            manifest_rows.append(entry)
            copied += 1 if ok else 0
            missing += 0 if ok else 1

        self.stdout.write(f"  {category}: processed")
        return copied, missing

    def _add_engagement_documentation_map_attachments(self, zf, manifest_rows, copied, missing):
        category = "engagement_documentation_map_attachments"
        for row in EngagementDocumentationMapAttachment.objects.select_related(
            "documentation_map__engagement__client",
            "documentation_map__engagement__fiscal_year",
            "documentation_map__engagement__service",
            "documentation_map__documentation",
        ):
            eng = row.documentation_map.engagement
            doc = row.documentation_map.documentation
            entry = [category, row.pk, eng.client.client_name, eng.fiscal_year.fy_no,
                     eng.service.service_desc, "", doc.standard_document, row.description or ""]
            ok = self._write_file(zf, category, row.pk, row.original_filename, row.file, entry)
            manifest_rows.append(entry)
            copied += 1 if ok else 0
            missing += 0 if ok else 1

        self.stdout.write(f"  {category}: processed")
        return copied, missing

    def _add_division_documentation_map_attachments(self, zf, manifest_rows, copied, missing):
        category = "engagement_division_documentation_map_attachments"
        for row in EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division__engagement__client",
            "documentation_map__division__engagement__fiscal_year",
            "documentation_map__division__engagement__service",
            "documentation_map__documentation",
        ):
            division = row.documentation_map.division
            eng = division.engagement
            doc = row.documentation_map.documentation
            entry = [category, row.pk, eng.client.client_name, eng.fiscal_year.fy_no,
                     eng.service.service_desc, division.division_name,
                     doc.standard_document, row.description or ""]
            ok = self._write_file(zf, category, row.pk, row.original_filename, row.file, entry)
            manifest_rows.append(entry)
            copied += 1 if ok else 0
            missing += 0 if ok else 1

        self.stdout.write(f"  {category}: processed")
        return copied, missing
