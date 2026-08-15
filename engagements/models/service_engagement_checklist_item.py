from django.conf import settings
from django.db import models

from .service_engagement_checklist_work_area import ServiceEngagementChecklistWorkArea

class ServiceEngagementChecklistItem(models.Model):
    """One actionable checklist line under a service work-area template."""

    work_area = models.ForeignKey(
        ServiceEngagementChecklistWorkArea,
        on_delete=models.CASCADE,
        related_name="items",
    )
    line_text = models.CharField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_service_engagement_checklist_items",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagement_checklist_items"
        ordering = ["work_area", "sort_order", "id"]

    def __str__(self):
        return self.line_text[:80]
