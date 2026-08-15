from django.conf import settings
from django.db import models

from hr.teams.models import TeamMember

from .engagement_division import EngagementDivision

class EngagementDivisionTeamAssignment(models.Model):
    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.PROTECT,
        related_name="division_assignments",
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
        related_name="created_engagement_division_team_assignments",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_division_team_assignments"
        ordering = [
            "division__engagement__client__client_name",
            "division__engagement__fiscal_year__fy_no",
            "division__engagement__service__service_desc",
            "division__division_name",
            "team_member__first_name",
            "team_member__last_name",
            "planned_start",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.division} | {self.team_member} | "
            f"{self.planned_start.isoformat()} - {self.planned_finish.isoformat()}"
        )
