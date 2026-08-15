from django.conf import settings
from django.db import models

from .engagement_division import EngagementDivision

class EngagementDivisionStatusRemark(models.Model):
    """Status remarks captured at engagement division level."""

    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_division_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_division_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)
