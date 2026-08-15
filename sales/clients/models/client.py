import re

from django.conf import settings
from django.db import models

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
