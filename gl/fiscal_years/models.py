from django.conf import settings
from django.db import models


class FiscalYear(models.Model):
    fy_no = models.CharField(max_length=4, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_fiscal_years",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fiscal_years"
        ordering = ["-fy_no"]

    def __str__(self):
        return f"{self.fy_no} ({self.start_date.isoformat()} to {self.end_date.isoformat()})"
