from django.conf import settings
from django.db import models

from .division_work_area import DivisionWorkArea

class DivisionWorkAreaStatusRemark(models.Model):
    """Standalone status remarks for a division work area."""

    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "division_work_area_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.work_area_id} | {self.created_on.isoformat()}"
