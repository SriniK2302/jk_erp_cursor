from django import forms

from engagements.models import FirmReferenceDocument

from .models import EngagementDocumentation
from .word_template import word_template_extension_ok


class EngagementDocumentationForm(forms.ModelForm):
    class Meta:
        model = EngagementDocumentation
        fields = [
            "standard_document",
            "filled_download_label",
            "word_template",
            "document_stage",
            "applicable_classifications",
        ]
        widgets = {
            "standard_document": forms.TextInput(attrs={"class": "input-long"}),
            "filled_download_label": forms.TextInput(
                attrs={
                    "class": "input-medium",
                    "placeholder": "e.g. MR 01",
                    "maxlength": "32",
                }
            ),
            "word_template": forms.FileInput(
                attrs={
                    "class": "input-long",
                    "accept": (
                        ".doc,.docx,application/msword,"
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                }
            ),
            "document_stage": forms.Select(attrs={"class": "input-medium"}),
            "applicable_classifications": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["applicable_classifications"].queryset = (
            self.fields["applicable_classifications"]
            .queryset.order_by("classification_name")
        )
        self.fields["word_template"].required = False

    def clean_word_template(self):
        f = self.cleaned_data.get("word_template")
        if not f:
            return f
        name = getattr(f, "name", "") or ""
        if not word_template_extension_ok(name):
            raise forms.ValidationError("Upload a Word file only (.doc or .docx).")
        return f

    def clean_standard_document(self):
        standard_document = (self.cleaned_data.get("standard_document") or "").strip()
        if not standard_document:
            raise forms.ValidationError("Standard document is required.")
        return standard_document

    def clean_filled_download_label(self):
        raw = (self.cleaned_data.get("filled_download_label") or "").strip()
        return raw[:32]

    def clean(self):
        cleaned_data = super().clean()

        standard_document = cleaned_data.get("standard_document")
        document_stage = cleaned_data.get("document_stage")

        if not standard_document or document_stage is None:
            return cleaned_data

        duplicates = EngagementDocumentation.objects.filter(
            standard_document=standard_document,
            document_stage=document_stage,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error(
                "standard_document",
                "Documentation with this standard document and stage already exists.",
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_upload = self.cleaned_data.get("word_template")

        if instance.pk and new_upload:
            old = EngagementDocumentation.objects.filter(pk=instance.pk).first()
            if old and old.word_template:
                old.word_template.delete(save=False)

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class FirmReferenceDocumentForm(forms.ModelForm):
    class Meta:
        model = FirmReferenceDocument
        fields = ["category", "tags", "is_active", "title", "description", "file"]
        widgets = {
            "category": forms.TextInput(
                attrs={
                    "class": "input-long",
                    "placeholder": "Type a category, or pick from the list below",
                    "autocomplete": "off",
                }
            ),
            "tags": forms.TextInput(
                attrs={
                    "class": "input-long",
                    "placeholder": "e.g. SA 230, sampling, Excel (comma-separated)",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": ""}),
            "title": forms.TextInput(attrs={"class": "input-long"}),
            "description": forms.Textarea(
                attrs={"class": "input-long", "rows": 3, "placeholder": "Optional notes"}
            ),
            "file": forms.FileInput(attrs={"class": "input-long"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].required = False
        self.fields["is_active"].required = False
        if self.instance.pk:
            self.fields["file"].required = False
            self.fields["file"].help_text = "Leave empty to keep the current file."
        seen = set()
        merged = []
        for s in FirmReferenceDocument.SUGGESTED_CATEGORIES:
            t = (s or "").strip()
            if not t or t.lower() in seen:
                continue
            seen.add(t.lower())
            merged.append(t)
        for c in FirmReferenceDocument.objects.values_list("category", flat=True).distinct():
            t = (c or "").strip()
            if not t or t.lower() in seen:
                continue
            seen.add(t.lower())
            merged.append(t)
        self.category_suggestions = sorted(merged, key=str.lower)

    def clean_category(self):
        c = (self.cleaned_data.get("category") or "").strip()
        if not c:
            raise forms.ValidationError("Category is required.")
        return c[:100]

    def clean_tags(self):
        raw = (self.cleaned_data.get("tags") or "").strip()
        if not raw:
            return ""
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return ", ".join(parts)[:500]

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f and not self.instance.pk:
            raise forms.ValidationError("Select a file to upload.")
        return f

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_upload = self.cleaned_data.get("file")
        if instance.pk and new_upload:
            old = FirmReferenceDocument.objects.filter(pk=instance.pk).first()
            if old and old.file:
                old.file.delete(save=False)
        if new_upload:
            client_name = getattr(new_upload, "name", "") or ""
            instance.original_filename = (client_name or "file")[:255]
        if commit:
            instance.save()
        return instance
