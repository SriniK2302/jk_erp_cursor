import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from .audit_query import AuditQuery

def _audit_query_attachment_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    qid = instance.query_id
    query = instance.query
    if query.engagement_work_area_id:
        eid = query.engagement_work_area.engagement_id
        wid = query.engagement_work_area_id
        return f"audit_query_attachments/engagement/{eid}/{wid}/{qid}/{unique}"
    did = query.division_work_area.division_id
    wid = query.division_work_area_id
    return f"audit_query_attachments/division/{did}/{wid}/{qid}/{unique}"


class AuditQueryAttachment(models.Model):
    query = models.ForeignKey(
        AuditQuery,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_audit_query_attachment_upload_to)
    original_filename = models.CharField(max_length=255)
    document_reference_no = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_audit_query_attachments",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_query_attachments"
        ordering = ["-created_on", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.document_reference_no = (self.document_reference_no or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


@receiver(post_delete, sender=AuditQueryAttachment)
def _delete_audit_query_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
