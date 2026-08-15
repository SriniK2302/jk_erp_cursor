from django.conf import settings
from django.db import models

from sales.services.models import Service

class ServiceEngagementChecklistWorkArea(models.Model):
    """
    Setup template: a named work area under a service, grouping engagement checklist
    line items the team should complete.
    """

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="engagement_checklist_work_areas",
    )
    name = models.CharField(max_length=200)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_service_engagement_checklist_work_areas",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagement_checklist_work_areas"
        ordering = ["service", "sort_order", "id"]

    def __str__(self):
        return f"{self.service.service_code} · {self.name}"
