"""
Unified work-document storage.

Consolidates (without deleting) the following existing tables:
  - audit_query_attachments
  - engagement_work_area_documents
  - division_work_area_documents
  - engagement_documentation_map_attachments
  - engagement_division_documentation_map_attachments

Old tables remain untouched until the unified table is verified working.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename


def _work_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"work_documents/{instance.scope_type}/{unique}"


class WorkDocument(models.Model):
    """One uploaded file, tagged with where it belongs and what kind it is."""

    # --- Flags ---
    SCOPE_ENGAGEMENT = "engagement"
    SCOPE_DIVISION = "division"
    SCOPE_CHOICES = [
        (SCOPE_ENGAGEMENT, "Engagement"),
        (SCOPE_DIVISION, "Division"),
    ]

    SOURCE_AUDIT_QUERY = "audit_query"
    SOURCE_WORK_AREA = "work_area"
    SOURCE_DOCUMENTATION_MAP = "documentation_map"
    SOURCE_CHOICES = [
        (SOURCE_AUDIT_QUERY, "Audit query"),
        (SOURCE_WORK_AREA, "Work area document"),
        (SOURCE_DOCUMENTATION_MAP, "Documentation map"),
    ]

    CLASSIFICATION_BLANK_TEMPLATE = "blank_template"
    CLASSIFICATION_OTHER = "other"
    CLASSIFICATION_CHOICES = [
        (CLASSIFICATION_BLANK_TEMPLATE, "Blank template"),
        (CLASSIFICATION_OTHER, "Other"),
    ]

    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    classification = models.CharField(
        max_length=20, choices=CLASSIFICATION_CHOICES, default=CLASSIFICATION_OTHER
    )

    # --- Where it belongs (only the relevant link is set per row) ---
    engagement = models.ForeignKey(
        "engagements.Engagement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_documents",
    )
    division = models.ForeignKey(
        "engagements.EngagementDivision",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_documents",
    )
    engagement_work_area = models.ForeignKey(
        "engagements.EngagementWorkArea",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_documents",
    )
    division_work_area = models.ForeignKey(
        "engagements.DivisionWorkArea",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_documents",
    )
    audit_query = models.ForeignKey(
        "engagements.AuditQuery",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="work_documents",
    )
    documentation = models.ForeignKey(
        "engagements.EngagementDocumentation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="work_documents",
    )

    # --- Document details ---
    document_date = models.DateField(null=True, blank=True)
    document_reference_no = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")

    # --- The file itself ---
    file = models.FileField(upload_to=_work_document_upload_to)
    original_filename = models.CharField(max_length=255)

    # --- Migration traceability: which old row this came from ---
    legacy_table = models.CharField(max_length=100, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    # --- Audit trail ---
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_work_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "work_documents"
        ordering = ["-created_on", "original_filename", "pk"]
        indexes = [
            models.Index(fields=["scope_type", "source_type", "classification"]),
            models.Index(fields=["legacy_table", "legacy_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        self.document_reference_no = (self.document_reference_no or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


@receiver(post_delete, sender=WorkDocument)
def _delete_work_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
