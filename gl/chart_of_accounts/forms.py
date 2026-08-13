from django import forms

from config.models import ChartOfAccount


class ChartOfAccountForm(forms.ModelForm):
    TYPE_RULES = {
        ChartOfAccount.TYPE_LIABILITY: (ChartOfAccount.PLBS_BS, 1001, 2999),
        ChartOfAccount.TYPE_ASSET: (ChartOfAccount.PLBS_BS, 3000, 4999),
        ChartOfAccount.TYPE_INCOME: (ChartOfAccount.PLBS_PL, 5000, 6999),
        ChartOfAccount.TYPE_EXPENSES: (ChartOfAccount.PLBS_PL, 7000, 9999),
    }

    class Meta:
        model = ChartOfAccount
        fields = ["account_name", "plbs", "plbs_type", "account_code"]
        widgets = {
            "account_name": forms.TextInput(attrs={"class": "input-medium"}),
            "account_code": forms.TextInput(
                attrs={
                    "class": "input-compact",
                    "inputmode": "numeric",
                    "pattern": r"\d{4}",
                    "minlength": "4",
                    "maxlength": "4",
                    "placeholder": "1001",
                }
            ),
            "plbs": forms.Select(attrs={"class": "input-compact"}),
            "plbs_type": forms.Select(attrs={"class": "input-compact"}),
        }

    @classmethod
    def _range_for_type(cls, plbs_type: str):
        rule = cls.TYPE_RULES.get(plbs_type)
        if not rule:
            return None, None, None
        return rule

    @classmethod
    def _next_available_account_code(cls, *, plbs_type: str | None = None) -> str:
        _, start, end = cls._range_for_type(plbs_type) if plbs_type else (None, 1001, 9999)
        if start is None or end is None:
            raise forms.ValidationError("Select PL/BS Type to auto-assign account code.")
        used_codes: set[int] = set()
        for raw in ChartOfAccount.objects.values_list("account_code", flat=True):
            s = str(raw or "").strip()
            if s.isdigit() and len(s) == 4:
                n = int(s)
                if start <= n <= end:
                    used_codes.add(n)
        for code in range(start, end + 1):
            if code not in used_codes:
                return str(code)
        raise forms.ValidationError(f"No account code available in range {start}-{end}.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plbs"].disabled = True
        self.fields["plbs"].required = False
        self.fields["account_code"].required = False
        self.fields["account_code"].widget.attrs["readonly"] = "readonly"
        is_edit = bool(getattr(self.instance, "pk", None))
        if is_edit:
            plbs_type = getattr(self.instance, "plbs_type", "") or ""
            expected_plbs, _, _ = self._range_for_type(plbs_type)
            if expected_plbs:
                self.fields["plbs"].initial = expected_plbs
            self.fields["account_code"].initial = str(self.instance.account_code or "")
        else:
            self.fields["plbs"].initial = ""
            self.fields["plbs_type"].initial = ""
            self.fields["account_code"].initial = ""

    def clean_account_code(self):
        if getattr(self.instance, "pk", None):
            return str(self.instance.account_code)

        raw = (self.cleaned_data.get("account_code") or self.initial.get("account_code") or "").strip()
        if not raw:
            return ""
        if not raw.isdigit() or len(raw) != 4:
            raise forms.ValidationError("Account code must be exactly 4 digits.")
        code = int(raw)
        if code < 1001 or code > 9999:
            raise forms.ValidationError("Account code must be between 1001 and 9999.")
        return str(code)

    def clean(self):
        cleaned_data = super().clean()
        plbs_type = cleaned_data.get("plbs_type")
        expected_plbs, start, end = self._range_for_type(plbs_type)
        if not expected_plbs:
            self.add_error("plbs_type", "Select a valid PL/BS Type.")
            return cleaned_data

        cleaned_data["plbs"] = expected_plbs

        if getattr(self.instance, "pk", None):
            raw_code = str(getattr(self.instance, "account_code", "") or "").strip()
            if not raw_code.isdigit():
                self.add_error("account_code", "Stored account code is invalid.")
                return cleaned_data
            code = int(raw_code)
            if code < start or code > end:
                self.add_error(
                    "plbs_type",
                    f"Existing account code {raw_code} does not belong to {plbs_type} range {start}-{end}.",
                )
            return cleaned_data

        cleaned_data["account_code"] = self._next_available_account_code(plbs_type=plbs_type)
        return cleaned_data
