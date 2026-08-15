import re

from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from engagements.models import Engagement

from .engagement_helpers import _format_fee_amount_display

class EngagementForm(forms.ModelForm):
    fee_amount = forms.CharField(
        required=False,
        label=Engagement._meta.get_field("fee_amount").verbose_name,
        widget=forms.TextInput(
            attrs={
                "class": "input-medium",
                "inputmode": "decimal",
                "autocomplete": "off",
                "data-amount-formatted": "1",
            }
        ),
    )

    class Meta:
        model = Engagement
        fields = [
            "client",
            "fiscal_year",
            "service",
            "fee_amount",
            "engagement_mail_id",
            "additional_mail_ids",
        ]
        widgets = {
            "client": forms.Select(attrs={"class": "input-medium"}),
            "fiscal_year": forms.Select(attrs={"class": "input-compact"}),
            "service": forms.Select(attrs={"class": "input-medium"}),
            "engagement_mail_id": forms.EmailInput(attrs={"class": "input-long"}),
            "additional_mail_ids": forms.Textarea(
                attrs={
                    "class": "input-long",
                    "rows": 3,
                    "placeholder": "Comma/newline separated additional email IDs",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.order_by(
            "client_name", "client_code"
        )
        self.fields["fiscal_year"].queryset = self.fields[
            "fiscal_year"
        ].queryset.order_by("-fy_no")
        self.fields["service"].queryset = self.fields["service"].queryset.order_by(
            "service_desc", "service_code"
        )
        if (
            not self.is_bound
            and self.instance
            and getattr(self.instance, "pk", None)
            and not (self.instance.engagement_mail_id or "").strip()
            and getattr(self.instance, "client", None) is not None
        ):
            self.initial.setdefault(
                "engagement_mail_id", (self.instance.client.mail_id or "").strip()
            )
        if (
            not self.is_bound
            and self.instance
            and getattr(self.instance, "pk", None)
            and not (self.instance.additional_mail_ids or "").strip()
            and getattr(self.instance, "client", None) is not None
            and (self.instance.client.additional_mail_ids or "").strip()
        ):
            self.initial.setdefault(
                "additional_mail_ids",
                (self.instance.client.additional_mail_ids or "").strip(),
            )
        fee_val = self.initial.get("fee_amount")
        if fee_val is None and self.instance and getattr(self.instance, "pk", None):
            fee_val = self.instance.fee_amount
        if fee_val not in (None, ""):
            self.initial["fee_amount"] = _format_fee_amount_display(fee_val)

    def clean_fee_amount(self):
        raw = self.cleaned_data.get("fee_amount")
        if raw is None:
            return None
        if isinstance(raw, Decimal):
            return raw if raw >= 0 else None
        text = str(raw).replace(",", "").strip()
        if not text:
            return None
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValidationError("Enter a valid fee amount.") from exc
        if amount < 0:
            raise ValidationError("Fee amount cannot be negative.")
        return amount

    @staticmethod
    def _split_mail_ids(raw: str):
        text = (raw or "").strip()
        if not text:
            return []
        parts = [p.strip() for p in re.split(r"[,\n;]+", text) if p.strip()]
        return parts

    def clean_engagement_mail_id(self):
        mail_id = (self.cleaned_data.get("engagement_mail_id") or "").strip()
        client = self.cleaned_data.get("client") or getattr(self.instance, "client", None)
        if not mail_id and client is not None:
            mail_id = (client.mail_id or "").strip()
        if mail_id:
            validate_email(mail_id)
        return mail_id

    def clean_additional_mail_ids(self):
        raw = self.cleaned_data.get("additional_mail_ids") or ""
        entries = self._split_mail_ids(raw)
        client = self.cleaned_data.get("client") or getattr(self.instance, "client", None)
        if not entries and client is not None:
            entries = self._split_mail_ids(client.additional_mail_ids or "")
        invalid = []
        for item in entries:
            try:
                validate_email(item)
            except ValidationError:
                invalid.append(item)
        if invalid:
            raise forms.ValidationError(
                "Invalid email(s): " + ", ".join(invalid[:5])
            )
        return ", ".join(entries)

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        fiscal_year = cleaned_data.get("fiscal_year")
        service = cleaned_data.get("service")
        if client and fiscal_year and service:
            qs = Engagement.objects.filter(
                client=client,
                fiscal_year=fiscal_year,
                service=service,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "An engagement already exists for this client, FY, and service."
                )
        return cleaned_data

