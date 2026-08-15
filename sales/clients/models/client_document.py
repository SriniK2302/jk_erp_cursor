import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from .client import Client


def _client_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"client_documents/{instance.client_id}/{unique}"


class ClientDocument(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to=_client_document_upload_to)
    original_filename = models.CharField(max_length=255)
    document_label = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Short label, e.g. MOA, AOA, Board resolution.",
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_client_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "client_documents"
        ordering = ["document_label", "original_filename", "pk"]
        app_label = "config"

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.document_label = (self.document_label or "").strip()
        self.notes = (self.notes or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.document_label:
            return f"{self.document_label}: {self.original_filename}"
        return self.original_filename

    @property
    def can_open_inline(self) -> bool:
        name = (self.original_filename or "").lower()
        if "." not in name:
            return False
        ext = name.rsplit(".", 1)[-1]
        return ext in {
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "webp",
            "txt",
        }


@receiver(post_delete, sender=ClientDocument)
def _delete_client_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
