from django.conf import settings
from django.db import models

from .engagement import Engagement

class EngagementDivision(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="divisions",
    )
    division_name = models.CharField(max_length=120)
    division_mail_ids = models.TextField(blank=True, default="")
    status = models.CharField(max_length=40, blank=True, default="")
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    closure_source = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_divisions",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_divisions"
        ordering = [
            "engagement__client__client_name",
            "engagement__fiscal_year__fy_no",
            "engagement__service__service_desc",
            "division_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "division_name"],
                name="uq_engagement_division_name",
            )
        ]

    def __str__(self):
        return f"{self.engagement} | {self.division_name}"
