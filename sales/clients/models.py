import re
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from sales.client_classifications.models import ClientClassification

_LEGAL_NAME_SUFFIX_PATTERNS = (
    r"\s+Private\s+Limited\s*$",
    r"\s+Pvt\.?\s+Ltd\.?\s*$",
    r"\s+Public\s+Limited\s*$",
    r"\s+Limited\s*$",
    r"\s+Ltd\.?\s*$",
    r"\s+LLP\s*$",
    r"\s+Inc\.?\s*$",
    r"\s+Corp\.?\s*$",
)


def _short_name_looks_like_code(short: str, code: str) -> bool:
    if not short or not code:
        return False
    short_u = short.strip().upper()
    code_u = code.strip().upper()
    if short_u == code_u:
        return True
    if len(short_u) <= 4 and (
        code_u.startswith(short_u) or short_u.startswith(code_u)
    ):
        return True
    return False


def _name_without_legal_suffix(name: str) -> str:
    text = (name or "").strip()
    for pattern in _LEGAL_NAME_SUFFIX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


class Client(models.Model):
    INVOICE_TAX_GST = "GST"
    INVOICE_TAX_IGST = "IGST"
    INVOICE_TAX_TYPE_CHOICES = [
        (INVOICE_TAX_GST, "GST (CGST + SGST)"),
        (INVOICE_TAX_IGST, "IGST"),
    ]

    client_name = models.CharField(max_length=150)
    client_short_name = models.CharField(max_length=60)
    client_code = models.CharField(max_length=4, unique=True)
    classification = models.ForeignKey(
        ClientClassification,
        on_delete=models.PROTECT,
        related_name="clients",
    )
    address_1 = models.CharField(max_length=200, blank=True, default="")
    address_2 = models.CharField(max_length=200, blank=True, default="")
    area = models.CharField(max_length=120, blank=True, default="")
    city_state_pincode = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(max_length=120, blank=True, default="")
    pincode = models.CharField(max_length=20, blank=True, default="")
    contact_person = models.CharField(max_length=120, blank=True, default="")
    mail_id = models.EmailField(max_length=254, blank=True, default="")
    additional_mail_ids = models.TextField(blank=True, default="")
    billing_gstn = models.CharField(max_length=20, blank=True, default="")
    invoice_tax_type = models.CharField(
        max_length=8,
        choices=INVOICE_TAX_TYPE_CHOICES,
        default=INVOICE_TAX_GST,
        help_text="GST: 9% CGST and 9% SGST on taxable value. IGST: 18% on taxable value.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_clients",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients"
        ordering = ["client_name"]
        app_label = "config"

    @property
    def display_name(self) -> str:
        """UI label: Client Short Name, never the 4-char client code."""
        short = (self.client_short_name or "").strip()
        code = (self.client_code or "").strip()
        if short and not _short_name_looks_like_code(short, code):
            return short
        derived = _name_without_legal_suffix(self.client_name or "")
        if derived:
            return derived
        return (self.client_name or "").strip() or "—"

    def __str__(self):
        return self.display_name


class ClientTaxProfile(models.Model):
    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name="tax_profile",
    )
    pan = models.CharField(max_length=10, blank=True)
    tax_password = models.CharField(max_length=255, blank=True)
    date_of_formation = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_client_tax_profiles",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_tax_profiles"
        ordering = ["client__client_name"]
        app_label = "config"

    def __str__(self):
        return f"Tax profile: {self.client.client_name}"


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


__all__ = ["Client", "ClientTaxProfile", "ClientDocument"]