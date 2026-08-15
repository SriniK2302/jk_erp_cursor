import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from .engagement_work_area import EngagementWorkArea

def _engagement_work_area_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    wid = instance.work_area_id
    eid = instance.work_area.engagement_id
    return f"engagement_work_area_documents/{eid}/{wid}/{unique}"


class EngagementWorkAreaDocument(models.Model):
    work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_date = models.DateField()
    description = models.CharField(max_length=255)
    document_reference_no = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    remarks = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=_engagement_work_area_document_upload_to)
    original_filename = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_work_area_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_work_area_documents"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        self.document_reference_no = (self.document_reference_no or "").strip()
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.work_area.work_area_name} | {self.original_filename}"


@receiver(post_delete, sender=EngagementWorkAreaDocument)
def _delete_engagement_work_area_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
