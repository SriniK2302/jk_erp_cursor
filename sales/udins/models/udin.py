from django.conf import settings
from django.db import models

from sales.clients.models import Client
from sales.services.models import Service

from sales.udins.udin_no import normalize_udin


class Udin(models.Model):
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
    create_date = models.DateField(null=True, blank=True)
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
    source_row = models.ForeignKey(
        "udins_source.UdinSource",
        on_delete=models.SET_NULL,
        related_name="udins",
        null=True,
        blank=True,
    )
    is_manual = models.BooleanField(default=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="udins",
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="udins",
        null=True,
        blank=True,
    )
    service_remarks = models.TextField(
        blank=True,
        default="",
        help_text="User-entered notes for this UDIN in addition to the master Service record.",
    )
    inv_no = models.CharField(max_length=60, blank=True, default="")
    inv_date = models.DateField(null=True, blank=True)
    inv_tv_amount = models.DecimalField(
        "Inv TV amt",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_invoiced = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_udins",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "udins"
        ordering = ["-created_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["udin"],
                name="uq_udins_udin",
            ),
        ]

    def save(self, *args, **kwargs):
        self.udin = normalize_udin(self.udin)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.udin
