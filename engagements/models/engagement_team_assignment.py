from django.conf import settings
from django.db import models

from hr.teams.models import TeamMember

from .engagement import Engagement

class EngagementTeamAssignment(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.PROTECT,
        related_name="engagement_assignments",
    )
    planned_start = models.DateField()
    planned_finish = models.DateField()
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When an assignment notification email was last sent to the team member.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_team_assignments",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_team_assignments"
        ordering = [
            "engagement__client__client_name",
            "engagement__fiscal_year__fy_no",
            "engagement__service__service_desc",
            "team_member__first_name",
            "team_member__last_name",
            "planned_start",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.engagement} | {self.team_member} | "
            f"{self.planned_start.isoformat()} - {self.planned_finish.isoformat()}"
        )
