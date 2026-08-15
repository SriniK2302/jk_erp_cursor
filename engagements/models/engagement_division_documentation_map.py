from django.conf import settings
from django.db import models

from .engagement_division import EngagementDivision
from .engagement_documentation import EngagementDocumentation

class EngagementDivisionDocumentationMap(models.Model):
    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="documentation_maps",
    )
    documentation = models.ForeignKey(
        EngagementDocumentation,
        on_delete=models.PROTECT,
        related_name="division_maps",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_division_documentation_maps",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_division_documentation_maps"
        ordering = [
            "division__engagement__client__client_name",
            "division__engagement__fiscal_year__fy_no",
            "division__engagement__service__service_desc",
            "division__division_name",
            "documentation__document_stage",
            "documentation__standard_document",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["division", "documentation"],
                name="uq_engagement_division_documentation_map",
            )
        ]

    def __str__(self):
        return f"{self.division} | {self.documentation}"
