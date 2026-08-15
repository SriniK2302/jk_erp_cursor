from django.conf import settings
from django.db import models


class ClientClassification(models.Model):
    classification_name = models.CharField(max_length=120, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_client_classifications",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_classifications"
        ordering = ["classification_name"]
        app_label = "config"

    def __str__(self):
        return self.classification_name
