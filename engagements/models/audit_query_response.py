from django.conf import settings
from django.db import models

from .audit_query import AuditQuery

class AuditQueryResponse(models.Model):
    """One response entry against an audit query."""

    query = models.ForeignKey(
        AuditQuery,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    response_date = models.DateField()
    responder_type = models.CharField(
        max_length=20,
        choices=AuditQuery.RESPONDER_TYPE_CHOICES,
        default=AuditQuery.RESPONDER_INTERNAL,
    )
    response_text = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_audit_query_responses",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_query_responses"
        ordering = ["response_date", "id"]

    def save(self, *args, **kwargs):
        self.response_text = (self.response_text or "").strip()
        super().save(*args, **kwargs)
