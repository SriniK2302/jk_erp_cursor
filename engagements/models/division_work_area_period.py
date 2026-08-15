from django.conf import settings
from django.db import models

from .division_work_area import DivisionWorkArea

class DivisionWorkAreaPeriod(models.Model):
    """One planned/actual window for a division-level work area."""

    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="schedule_rows",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    closure_source = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_schedule_rows",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "division_work_area_periods"
        ordering = ["planned_start", "id"]
        verbose_name = "Division work area schedule row"
        verbose_name_plural = "Division work area schedule rows"

    def __str__(self):
        planned_start = self.planned_start.isoformat() if self.planned_start else "—"
        planned_finish = self.planned_finish.isoformat() if self.planned_finish else "—"
        return (
            f"{self.work_area.work_area_name} | "
            f"{planned_start}–{planned_finish}"
        )
