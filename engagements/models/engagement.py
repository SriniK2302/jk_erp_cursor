from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from gl.fiscal_years.models import FiscalYear
from sales.clients.models import Client
from sales.services.models import Service

class Engagement(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    engagement_mail_id = models.EmailField(max_length=254, blank=True, default="")
    additional_mail_ids = models.TextField(blank=True, default="")
    fee_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=(
            "Optional engagement-level fee (e.g. audit fee). "
            "Certification engagements may use per-certificate amounts later."
        ),
    )
    status = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagements",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagements"
        ordering = ["client__client_name", "fiscal_year__fy_no", "service__service_desc"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "fiscal_year", "service"],
                name="uq_engagement_client_fy_service",
            )
        ]

    def __str__(self):
        return f"{self.client.client_code}-{self.fiscal_year.fy_no}-{self.service.service_code}"
