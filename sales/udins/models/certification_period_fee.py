from django.db import models

from sales.clients.models import Client


class CertificationPeriodFee(models.Model):
    """
    Certification Inv TV amt per client for a calendar period (from–to on document signing).
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="certification_period_fees",
    )
    from_date = models.DateField()
    to_date = models.DateField()
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "udins_certification_period_fees"
        ordering = ["client__client_name", "-from_date", "-id"]

    def __str__(self):
        return f"{self.client} · {self.from_date} – {self.to_date} · {self.fee_amount}"
