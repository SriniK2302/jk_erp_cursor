from django.conf import settings
from django.db import models

from .engagement import Engagement
from .engagement_documentation import EngagementDocumentation

class EngagementDocumentationMap(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="documentation_maps",
    )
    documentation = models.ForeignKey(
        EngagementDocumentation,
        on_delete=models.PROTECT,
        related_name="engagement_maps",
    )
    documentation_date = models.DateField(
        help_text="Date used to order mapped documentation (e.g. planned or signed date).",
    )
    representation_point_matrix = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-engagement acknowledgment matrix for MR 02 (and similar) items: "
            "point id → {status, notes?}. Empty when not used."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentation_maps",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_documentation_maps"
        ordering = [
            "documentation_date",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "documentation"],
                name="uq_engagement_documentation_map",
            )
        ]

    def __str__(self):
        return f"{self.engagement} | {self.documentation}"
