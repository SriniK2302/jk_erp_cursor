import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from .engagement_documentation_map import EngagementDocumentationMap

def _engagement_documentation_map_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    mid = instance.documentation_map_id
    eid = instance.documentation_map.engagement_id
    return f"engagement_documentation/{eid}/{mid}/{unique}"


class EngagementDocumentationMapAttachment(models.Model):
    documentation_map = models.ForeignKey(
        EngagementDocumentationMap,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_engagement_documentation_map_upload_to)
    original_filename = models.CharField(max_length=255)
    document_date = models.DateField(
        help_text="Date of the underlying document (e.g. letter or signing date).",
    )
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentation_attachments",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_documentation_map_attachments"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


@receiver(post_delete, sender=EngagementDocumentationMapAttachment)
def _delete_engagement_documentation_map_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
