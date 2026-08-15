from django.db import models

from .engagement import Engagement
from .work_area_base import WorkAreaBase

class EngagementWorkArea(WorkAreaBase):
    """Work area scoped to the whole engagement (no division)."""

    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="work_areas",
    )
    service_checklist_work_area = models.ForeignKey(
        "ServiceEngagementChecklistWorkArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="engagement_work_area_instances",
        help_text=(
            "Optional link to the Service engagement checklist work-area template "
            "(setup) used when this row was picked there—convenience for that pointer "
            "only; cleared if that template is deleted. Other masters are unrelated."
        ),
    )
    documentation = models.ForeignKey(
        "EngagementDocumentation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="engagement_work_areas",
        help_text="Broader documentation this work area falls under.",
    )

    class Meta:
        db_table = "engagement_work_areas"
        ordering = ["sort_order", "work_area_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "work_area_name"],
                name="uq_engagement_work_area_name",
            ),
            models.UniqueConstraint(
                fields=["engagement", "service_checklist_work_area"],
                condition=models.Q(service_checklist_work_area__isnull=False),
                name="uq_engagement_work_area_service_template",
            ),
        ]

    def __str__(self):
        return f"{self.engagement} | {self.work_area_name}"
