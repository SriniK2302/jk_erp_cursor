from django.conf import settings
from django.db import models


class Service(models.Model):
    service_desc = models.CharField(max_length=150)
    service_code = models.CharField(max_length=4, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_services",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "services"
        ordering = ["service_desc"]

    def __str__(self):
        return f"{self.service_desc} ({self.service_code})"
