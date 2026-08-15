from django.conf import settings
from django.db import models

class AuditQueryMailDraftLog(models.Model):
    """Audit trail for draft emails generated from work-area notes."""

    audit_query = models.ForeignKey(
        "AuditQuery",
        on_delete=models.CASCADE,
        related_name="mail_draft_logs",
    )
    recipient_to = models.TextField(blank=True, default="")
    recipient_cc = models.TextField(blank=True, default="")
    subject = models.CharField(max_length=255)
    drafted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_audit_query_mail_drafts",
    )
    drafted_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_query_mail_draft_logs"
        ordering = ["-drafted_on", "-id"]

    def __str__(self):
        return f"{self.audit_query_id} | {self.subject}"
