from django.conf import settings
from django.db import models

class WorkAreaBase(models.Model):
    """Shared fields for engagement-level vs division-level work areas."""

    work_area_name = models.CharField(max_length=150)
    sort_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=40, blank=True, default="")
    closure_source = models.CharField(max_length=40, blank=True, default="")
    monetary_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional monetary amount for this work area (from work area notes).",
    )
    monetary_amount_unit = models.CharField(
        max_length=20,
        blank=True,
        default="lakhs",
        help_text="Unit for monetary_amount (lakhs, rs, crores).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.work_area_name
