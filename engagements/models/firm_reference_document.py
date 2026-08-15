import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

def _firm_reference_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "file"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"firm_reference_documents/{unique}"


class FirmReferenceDocument(models.Model):
    """Firm-wide reference file in Setup (not tied to documentation stage)."""

    DEFAULT_CATEGORY = "General / other"
    SUGGESTED_CATEGORIES = [
        "Audit methodology",
        "Tax",
        "IT & tools",
        "Firm policies",
        "Templates (non-client-specific)",
        "External standards & circulars",
        DEFAULT_CATEGORY,
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=100,
        default=DEFAULT_CATEGORY,
        db_index=True,
        help_text="Use a suggested name or type your own; this is shown in lists and search.",
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Comma-separated keywords for search (e.g. SA 230, sampling, Excel).",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive items stay in the database but are hidden from the default list.",
    )
    file = models.FileField(upload_to=_firm_reference_document_upload_to)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_firm_reference_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "firm_reference_documents"
        ordering = ["category", "title", "pk"]

    def save(self, *args, **kwargs):
        self.title = (self.title or "").strip()
        self.category = (self.category or "").strip() or self.DEFAULT_CATEGORY
        self.description = (self.description or "").strip()
        self.tags = (self.tags or "").strip()
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            if "_" in base:
                prefix, sep, suffix = base.partition("_")
                if (
                    len(prefix) == 32
                    and sep == "_"
                    and all(c in "0123456789abcdef" for c in prefix.lower())
                ):
                    self.original_filename = (suffix or "file")[:255]
                else:
                    self.original_filename = (base or "file")[:255]
            else:
                self.original_filename = (base or "file")[:255]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


@receiver(post_delete, sender=FirmReferenceDocument)
def _delete_firm_reference_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
