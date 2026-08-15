from django.conf import settings
from django.db import models

from sales.udins.udin_no import normalize_udin


class UdinSource(models.Model):
    s_no = models.PositiveIntegerField(null=True, blank=True)
    udin = models.CharField(max_length=60)
    mrn = models.CharField(max_length=30, blank=True, default="")
    firm = models.CharField(max_length=255, blank=True, default="")
    document_type = models.CharField(max_length=120, blank=True, default="")
    document_sub_type = models.CharField(max_length=120, blank=True, default="")
    other_doc = models.CharField(max_length=120, blank=True, default="")
    document_description = models.CharField(max_length=255, blank=True, default="")
    date_of_signing_of_document = models.CharField(max_length=30, blank=True, default="")
    ay_fy = models.CharField(max_length=40, blank=True, default="")
    created_date_time = models.CharField(max_length=60, blank=True, default="")
    remarks = models.TextField(blank=True, default="")
    status = models.CharField(max_length=40, blank=True, default="")
    particulars_1 = models.CharField(max_length=180, blank=True, default="")
    figures_values_1 = models.CharField(max_length=180, blank=True, default="")
    particulars_2 = models.CharField(max_length=180, blank=True, default="")
    figures_values_2 = models.CharField(max_length=180, blank=True, default="")
    particulars_3 = models.CharField(max_length=180, blank=True, default="")
    figures_values_3 = models.CharField(max_length=180, blank=True, default="")
    particulars_4 = models.CharField(max_length=180, blank=True, default="")
    figures_values_4 = models.CharField(max_length=180, blank=True, default="")
    copied_to_udins = models.BooleanField(default=False, db_index=True)
    copied_on = models.DateTimeField(null=True, blank=True)
    source_payload = models.JSONField(default=dict, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="imported_udin_source_rows",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "udins_source"
        ordering = ["-created_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["udin"],
                name="uq_udins_source_udin",
            ),
        ]

    def save(self, *args, **kwargs):
        self.udin = normalize_udin(self.udin)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.udin or f"UDIN Source #{self.pk}"
