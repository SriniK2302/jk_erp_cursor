from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only log of business data updates and deletes. Do not modify rows from application code."""

    class Action(models.TextChoices):
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"

    action = models.CharField(max_length=10, choices=Action.choices, db_index=True)
    model_label = models.CharField(
        max_length=120,
        db_index=True,
        help_text="Django model label, e.g. config.Client",
    )
    object_id = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} {self.model_label} pk={self.object_id} @ {self.created_at}"
