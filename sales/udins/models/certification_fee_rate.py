from django.db import models

from sales.clients.models import Client
from sales.services.models import Service


class CertificationFeeRate(models.Model):
    """
    Certification fee per Client + Service combination.
    Used to bulk-set Udin.inv_tv_amount for rows with matching client and service
    only when inv_tv_amount is unset (null); existing values are not overwritten.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="certification_fee_rates",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="certification_fee_rates",
    )
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "udins_certification_fee_rates"
        constraints = [
            models.UniqueConstraint(
                fields=["client", "service"],
                name="uniq_udins_cert_fee_client_service",
            )
        ]
        ordering = ["client__client_name", "service__service_desc"]

    def __str__(self):
        return f"{self.client} · {self.service} · {self.fee_amount}"
