from django.conf import settings
from django.db import models

from .division_work_area_team_assignment import DivisionWorkAreaTeamAssignment

class DivisionWorkAreaConfirmationMailLog(models.Model):
    """Audit trail for division work-area confirmation mails."""

    assignment = models.ForeignKey(
        DivisionWorkAreaTeamAssignment,
        on_delete=models.CASCADE,
        related_name="confirmation_mail_logs",
    )
    mail_type = models.CharField(max_length=30, default="confirmation")
    recipient_email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=255)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_division_work_area_confirmation_mails",
    )
    sent_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "division_work_area_confirmation_mail_logs"
        ordering = ["-sent_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "mail_type"],
                name="uq_division_work_area_confirmation_mail_once",
            )
        ]

    def __str__(self):
        return f"{self.assignment_id} | {self.recipient_email} | {self.mail_type}"
