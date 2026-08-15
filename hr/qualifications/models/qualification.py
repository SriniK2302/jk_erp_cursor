from django.conf import settings
from django.db import models


class Qualification(models.Model):
    qualification_desc = models.CharField(max_length=150)
    qualification_code = models.CharField(max_length=4, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_qualifications",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qualifications"
        ordering = ["qualification_desc"]

    def __str__(self):
        return f"{self.qualification_desc} ({self.qualification_code})"
