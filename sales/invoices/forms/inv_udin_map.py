from decimal import Decimal, InvalidOperation

from django import forms
from django.db.models import F, Func, Q, Value
from django.db.models.functions import NullIf
from django.forms import BaseFormSet, formset_factory

from sales.udins.models import Udin

from sales.invoices.invoice_lines import money2
from sales.invoices.models import InvUdinMap


def udin_choice_queryset_for_invoice(*, invoice_pk: int | None = None):
    """
    Selectable UDINs: not invoiced (is_invoiced False and not on another invoice's map),
    plus UDINs already linked to this invoice when editing.
    """
    base = (
        Udin.objects.filter(client__isnull=False, service__isnull=False)
        .select_related("client", "service")
        .annotate(
            signed_doc_date_sort=Func(
                NullIf(F("date_of_signing_of_document"), Value("")),
                Value("DD-MM-YYYY"),
                function="TO_DATE",
            )
        )
        .order_by("signed_doc_date_sort", "client__client_short_name", "udin")
    )
    on_this_ids: list[int] = []
    if invoice_pk:
        on_this_ids = list(
            InvUdinMap.objects.filter(invoice_id=invoice_pk).values_list("udin_id", flat=True)
        )
    on_other_maps = InvUdinMap.objects.all()
    if invoice_pk:
        on_other_maps = on_other_maps.exclude(invoice_id=invoice_pk)
    blocked_map = set(on_other_maps.values_list("udin_id", flat=True).distinct())

    q = Q(is_invoiced=False)
    if on_this_ids:
        q |= Q(pk__in=on_this_ids)
    qs = base.filter(q)
    if blocked_map:
        qs = qs.exclude(pk__in=blocked_map)
    return qs.distinct()


class InvUdinMapForm(forms.Form):
    """One UDIN fee line. A plain form (not a ModelForm): map rows are wholesale
    rebuilt on every save, so binding row PKs would break stale resubmissions."""

    udin = forms.ModelChoiceField(
        queryset=Udin.objects.none(),
        required=False,
        label="UDIN",
        widget=forms.Select(attrs={"class": "inv-map-udin-select"}),
    )
    service_desc = forms.CharField(
        required=False,
        max_length=255,
        label="Description",
        widget=forms.TextInput(
            attrs={
                "class": "input-medium",
                "placeholder": "e.g. Fee for …",
                "autocomplete": "off",
            }
        ),
    )
    line_amount = forms.CharField(
        required=False,
        label="Amount (Rs)",
        widget=forms.TextInput(
            attrs={"inputmode": "decimal", "autocomplete": "off", "class": "inv-map-amount"}
        ),
    )

    def __init__(self, *args, **kwargs):
        self._invoice_pk = kwargs.pop("invoice_pk", None)
        super().__init__(*args, **kwargs)
        self.fields["udin"].queryset = udin_choice_queryset_for_invoice(invoice_pk=self._invoice_pk)
        self.fields["udin"].empty_label = "Choose UDIN…"
        self.fields["udin"].label_from_instance = (
            lambda u: (
                f"{u.udin} — {u.client.client_short_name} · {u.service.service_desc}"
                f" · Signed: {(u.date_of_signing_of_document or '—')}"
            )
        )

    def clean_line_amount(self):
        raw = (self.cleaned_data.get("line_amount") or "").strip()
        if raw == "":
            return None
        try:
            return money2(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            raise forms.ValidationError("Enter a valid amount.")


class BaseInvUdinMapFormSet(BaseFormSet):
    def __init__(self, *args, invoice_pk=None, **kwargs):
        self.invoice_pk = invoice_pk
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["invoice_pk"] = self.invoice_pk
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active = []
        client_ids = set()
        udin_ids = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                continue
            udin = cd.get("udin")
            amt = cd.get("line_amount")
            if not udin and amt in (None, "") and not (cd.get("service_desc") or "").strip():
                continue
            if not udin:
                form.add_error("udin", "Select a UDIN for each fee line.")
                continue
            if amt is None or amt < 0:
                form.add_error("line_amount", "Enter a non-negative amount for each fee line.")
                continue
            client_ids.add(udin.client_id)
            udin_ids.append(udin.pk)
            active.append((udin, cd.get("service_desc") or "", amt))
        if any(self.errors):
            return
        if len(client_ids) > 1:
            raise forms.ValidationError("All UDINs on one invoice must belong to the same client.")
        if not active:
            raise forms.ValidationError("Add at least one UDIN line (zero amount is allowed).")
        self._cleaned_map_rows = active
        self._duplicate_udin = len(udin_ids) != len(set(udin_ids))


InvUdinMapFormSet = formset_factory(
    InvUdinMapForm,
    formset=BaseInvUdinMapFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
)
