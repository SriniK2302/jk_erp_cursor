from django.conf import settings
from django.db import models


class Grade(models.Model):
    grade_desc = models.CharField(max_length=150)
    grade_code = models.CharField(max_length=4, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_grades",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "grades"
        ordering = ["grade_desc"]

    def __str__(self):
        return f"{self.grade_desc} ({self.grade_code})"
