from django.conf import settings
from django.db import models

from .client import Client


class ClientTaxProfile(models.Model):
    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name="tax_profile",
    )
    pan = models.CharField(max_length=10, blank=True)
    tax_password = models.CharField(max_length=255, blank=True)
    date_of_formation = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_client_tax_profiles",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_tax_profiles"
        ordering = ["client__client_name"]
        app_label = "config"

    def __str__(self):
        return f"Tax profile: {self.client.client_name}"
