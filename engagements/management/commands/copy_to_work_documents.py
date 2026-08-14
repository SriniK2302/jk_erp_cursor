"""
Copy (never move/delete) rows and files from the 5 legacy attachment tables
into the new unified `work_documents` table.

Safe to re-run: each run first deletes rows it previously copied (matched by
legacy_table + legacy_id) and re-copies fresh, so nothing is duplicated.

Old tables and their files are never touched or deleted by this command.

If a source file is missing on disk, that row is skipped (not copied) and
reported in a list at the end -- it does not stop the rest of the copy.

Usage:
    python manage.py copy_to_work_documents
    python manage.py copy_to_work_documents --dry-run
"""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from engagements.models import (
    AuditQueryAttachment,
    DivisionWorkAreaDocument,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDocumentationMapAttachment,
    EngagementWorkAreaDocument,
    WorkDocument,
)


def _combine_description(description: str, remarks: str) -> str:
    description = (description or "").strip()
    remarks = (remarks or "").strip()
    if description and remarks:
        return f"{description}\n\nRemarks: {remarks}"
    return description or remarks


class Command(BaseCommand):
    help = "Copy legacy attachment rows/files into the unified work_documents table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be copied without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        self.skipped = []
        total = 0

        total += self._copy_audit_query_attachments(dry_run)
        total += self._copy_engagement_work_area_documents(dry_run)
        total += self._copy_division_work_area_documents(dry_run)
        total += self._copy_engagement_documentation_map_attachments(dry_run)
        total += self._copy_division_documentation_map_attachments(dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Would copy {total} rows total."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Copied {total} rows total."))

        if self.skipped:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(
                f"Skipped {len(self.skipped)} row(s) with missing files on disk:"
            ))
            for item in self.skipped:
                self.stdout.write(
                    f"  - {item['legacy_table']} id={item['legacy_id']} "
                    f"file={item['file_path']}"
                )
        else:
            self.stdout.write("No missing files. All rows copied cleanly.")

    def _reset_source(self, legacy_table: str, dry_run: bool) -> None:
        if not dry_run:
            WorkDocument.objects.filter(legacy_table=legacy_table).delete()

    def _duplicate_file(self, wd: WorkDocument, source_field) -> bool:
        """
        Read the source file's bytes and save as a brand-new physical file.
        Returns False (and records the skip) if the source file is missing.
        """
        try:
            source_field.open("rb")
            try:
                data = source_field.read()
            finally:
                source_field.close()
        except (FileNotFoundError, OSError):
            self.skipped.append({
                "legacy_table": wd.legacy_table,
                "legacy_id": wd.legacy_id,
                "file_path": getattr(source_field, "name", "") or "",
            })
            return False

        wd.file.save(wd.original_filename or "file", ContentFile(data), save=False)
        return True

    @transaction.atomic
    def _copy_audit_query_attachments(self, dry_run: bool) -> int:
        legacy_table = "audit_query_attachments"
        self._reset_source(legacy_table, dry_run)
        count = 0
        for row in AuditQueryAttachment.objects.select_related(
            "query", "query__engagement_work_area__engagement",
            "query__division_work_area__division",
        ):
            query = row.query
            if query.engagement_work_area_id:
                scope_type = WorkDocument.SCOPE_ENGAGEMENT
                engagement = query.engagement_work_area.engagement
                engagement_work_area = query.engagement_work_area
                division = None
                division_work_area = None
            else:
                scope_type = WorkDocument.SCOPE_DIVISION
                division = query.division_work_area.division
                division_work_area = query.division_work_area
                engagement = None
                engagement_work_area = None

            if dry_run:
                count += 1
                continue

            wd = WorkDocument(
                scope_type=scope_type,
                source_type=WorkDocument.SOURCE_AUDIT_QUERY,
                classification=WorkDocument.CLASSIFICATION_OTHER,
                engagement=engagement,
                division=division,
                engagement_work_area=engagement_work_area,
                division_work_area=division_work_area,
                audit_query=query,
                document_reference_no=row.document_reference_no,
                original_filename=row.original_filename,
                legacy_table=legacy_table,
                legacy_id=row.pk,
                created_by=row.created_by,
            )
            if not self._duplicate_file(wd, row.file):
                continue
            wd.save()
            WorkDocument.objects.filter(pk=wd.pk).update(created_on=row.created_on)
            count += 1

        self.stdout.write(f"  audit_query_attachments: {count} rows")
        return count

    @transaction.atomic
    def _copy_engagement_work_area_documents(self, dry_run: bool) -> int:
        legacy_table = "engagement_work_area_documents"
        self._reset_source(legacy_table, dry_run)
        count = 0
        for row in EngagementWorkAreaDocument.objects.select_related("work_area__engagement"):
            if dry_run:
                count += 1
                continue

            wd = WorkDocument(
                scope_type=WorkDocument.SCOPE_ENGAGEMENT,
                source_type=WorkDocument.SOURCE_WORK_AREA,
                classification=WorkDocument.CLASSIFICATION_OTHER,
                engagement=row.work_area.engagement,
                engagement_work_area=row.work_area,
                document_date=row.document_date,
                document_reference_no=row.document_reference_no,
                description=_combine_description(row.description, row.remarks),
                original_filename=row.original_filename,
                legacy_table=legacy_table,
                legacy_id=row.pk,
                created_by=row.created_by,
            )
            if not self._duplicate_file(wd, row.file):
                continue
            wd.save()
            WorkDocument.objects.filter(pk=wd.pk).update(created_on=row.created_on)
            count += 1

        self.stdout.write(f"  engagement_work_area_documents: {count} rows")
        return count

    @transaction.atomic
    def _copy_division_work_area_documents(self, dry_run: bool) -> int:
        legacy_table = "division_work_area_documents"
        self._reset_source(legacy_table, dry_run)
        count = 0
        for row in DivisionWorkAreaDocument.objects.select_related("work_area__division"):
            if dry_run:
                count += 1
                continue

            wd = WorkDocument(
                scope_type=WorkDocument.SCOPE_DIVISION,
                source_type=WorkDocument.SOURCE_WORK_AREA,
                classification=WorkDocument.CLASSIFICATION_OTHER,
                division=row.work_area.division,
                division_work_area=row.work_area,
                document_date=row.document_date,
                document_reference_no=row.document_reference_no,
                description=_combine_description(row.description, row.remarks),
                original_filename=row.original_filename,
                legacy_table=legacy_table,
                legacy_id=row.pk,
                created_by=row.created_by,
            )
            if not self._duplicate_file(wd, row.file):
                continue
            wd.save()
            WorkDocument.objects.filter(pk=wd.pk).update(created_on=row.created_on)
            count += 1

        self.stdout.write(f"  division_work_area_documents: {count} rows")
        return count

    @transaction.atomic
    def _copy_engagement_documentation_map_attachments(self, dry_run: bool) -> int:
        legacy_table = "engagement_documentation_map_attachments"
        self._reset_source(legacy_table, dry_run)
        count = 0
        for row in EngagementDocumentationMapAttachment.objects.select_related(
            "documentation_map__engagement", "documentation_map__documentation"
        ):
            if dry_run:
                count += 1
                continue

            wd = WorkDocument(
                scope_type=WorkDocument.SCOPE_ENGAGEMENT,
                source_type=WorkDocument.SOURCE_DOCUMENTATION_MAP,
                classification=WorkDocument.CLASSIFICATION_OTHER,
                engagement=row.documentation_map.engagement,
                documentation=row.documentation_map.documentation,
                document_date=row.document_date,
                description=row.description,
                original_filename=row.original_filename,
                legacy_table=legacy_table,
                legacy_id=row.pk,
                created_by=row.created_by,
            )
            if not self._duplicate_file(wd, row.file):
                continue
            wd.save()
            WorkDocument.objects.filter(pk=wd.pk).update(created_on=row.created_on)
            count += 1

        self.stdout.write(f"  engagement_documentation_map_attachments: {count} rows")
        return count

    @transaction.atomic
    def _copy_division_documentation_map_attachments(self, dry_run: bool) -> int:
        legacy_table = "engagement_division_documentation_map_attachments"
        self._reset_source(legacy_table, dry_run)
        count = 0
        for row in EngagementDivisionDocumentationMapAttachment.objects.select_related(
            "documentation_map__division", "documentation_map__documentation"
        ):
            if dry_run:
                count += 1
                continue

            wd = WorkDocument(
                scope_type=WorkDocument.SCOPE_DIVISION,
                source_type=WorkDocument.SOURCE_DOCUMENTATION_MAP,
                classification=WorkDocument.CLASSIFICATION_OTHER,
                division=row.documentation_map.division,
                documentation=row.documentation_map.documentation,
                document_date=row.document_date,
                description=row.description,
                original_filename=row.original_filename,
                legacy_table=legacy_table,
                legacy_id=row.pk,
                created_by=row.created_by,
            )
            if not self._duplicate_file(wd, row.file):
                continue
            wd.save()
            WorkDocument.objects.filter(pk=wd.pk).update(created_on=row.created_on)
            count += 1

        self.stdout.write(f"  engagement_division_documentation_map_attachments: {count} rows")
        return count
    