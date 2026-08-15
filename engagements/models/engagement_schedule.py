from django.conf import settings
from django.db import models

from .engagement import Engagement

class EngagementSchedule(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    planned_start = models.DateField()
    planned_finish = models.DateField()
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_schedules",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_schedules"
        ordering = ["planned_start", "id"]

    def __str__(self):
        return (
            f"{self.engagement} | {self.planned_start.isoformat()} - "
            f"{self.planned_finish.isoformat()}"
        )
