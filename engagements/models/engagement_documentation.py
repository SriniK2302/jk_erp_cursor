import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from sales.client_classifications.models import ClientClassification

def _engagement_documentation_word_template_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "template"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"engagement_documentation_templates/{unique}"


class EngagementDocumentation(models.Model):
    PRE_ENGAGEMENT = "pre_engagement"
    POST_ENGAGEMENT = "post_engagement"
    ENGAGEMENT_WORKING_PAPERS = "working_papers"
    ENGAGEMENT_PLANNING = "engagement_planning"
    ENGAGEMENT_CONCLUSION = "engagement_conclusion"
    DOCUMENT_STAGE_CHOICES = [
        (PRE_ENGAGEMENT, "Pre-engagement"),
        (POST_ENGAGEMENT, "Post-engagement"),
        (ENGAGEMENT_WORKING_PAPERS, "Engagement Working Papers"),
        (ENGAGEMENT_PLANNING, "Engagement Planning"),
        (ENGAGEMENT_CONCLUSION, "Engagement Conclusion"),
    ]

    standard_document = models.CharField(max_length=180)
    filled_download_label = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Optional short suffix for Fill Word downloads, after date · FY · client code · "
            "service code (e.g. MR 01). Leave blank to build a short name from the standard document."
        ),
    )
    word_template = models.FileField(
        upload_to=_engagement_documentation_word_template_upload_to,
        blank=True,
        null=True,
        help_text="Optional Word template (.doc or .docx) for this standard document.",
    )
    document_stage = models.CharField(max_length=30, choices=DOCUMENT_STAGE_CHOICES)
    applicable_classifications = models.ManyToManyField(
        ClientClassification,
        related_name="engagement_documentations",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentations",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_documentations"
        ordering = [
            "document_stage",
            "standard_document",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["standard_document", "document_stage"],
                name="uq_engagementdocumentation_standard_document_stage",
            )
        ]

    @property
    def is_mr02_catalog_item(self) -> bool:
        """Setup row uses MR 02 suffix (enables per-engagement MR 02 acknowledgment matrix)."""
        from engagements.documentations.representation_matrix import is_mr02_documentation

        return is_mr02_documentation(self)

    @property
    def word_template_display_name(self) -> str:
        """Uploaded filename for display (stored as ``{uuid32}_{original}``)."""
        if not self.word_template:
            return ""
        raw = getattr(self.word_template, "name", "") or ""
        base = raw.replace("\\", "/").rsplit("/", 1)[-1]
        if "_" in base:
            prefix, sep, suffix = base.partition("_")
            if (
                len(prefix) == 32
                and sep == "_"
                and all(c in "0123456789abcdef" for c in prefix.lower())
            ):
                return suffix or "template"
        return base or "template"

    def __str__(self):
        names = ", ".join(
            self.applicable_classifications.order_by(
                "classification_name"
            ).values_list("classification_name", flat=True)
        )
        label = names or "—"
        return f"{self.standard_document} ({self.get_document_stage_display()} — {label})"


@receiver(post_delete, sender=EngagementDocumentation)
def _delete_engagement_documentation_word_template_file(sender, instance, **kwargs):
    if instance.word_template:
        instance.word_template.delete(save=False)
