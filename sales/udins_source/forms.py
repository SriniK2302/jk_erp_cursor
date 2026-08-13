import json

from django import forms

from .models import UdinSourceHeaderMap


class UdinSourceImportForm(forms.Form):
    source_file = forms.FileField()


class UdinSourceHeaderMapForm(forms.Form):
    mapping_json = forms.CharField(widget=forms.Textarea(attrs={"rows": 16}))

    def clean_mapping_json(self):
        raw = (self.cleaned_data.get("mapping_json") or "").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise forms.ValidationError("Mapping must be a JSON object.")
        for canonical, aliases in parsed.items():
            if not isinstance(canonical, str) or not canonical.strip():
                raise forms.ValidationError("All mapping keys must be non-empty strings.")
            if not isinstance(aliases, list) or not all(
                isinstance(item, str) and item.strip() for item in aliases
            ):
                raise forms.ValidationError(
                    "Each mapping value must be an array of non-empty header strings."
                )
        return parsed

    @staticmethod
    def initial_json(mapping: dict) -> str:
        return json.dumps(mapping, indent=2, ensure_ascii=True)


def save_header_map(row: UdinSourceHeaderMap, mapping: dict, *, user):
    row.mapping_json = mapping
    row.updated_by = user
    row.save(update_fields=["mapping_json", "updated_by", "updated_on"])
