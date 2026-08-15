from django.conf import settings
from django.db import models

from hr.teams.models import TeamMember

from .division_work_area import DivisionWorkArea

class DivisionWorkAreaTeamAssignment(models.Model):
    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.PROTECT,
        related_name="division_work_area_assignments",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    assignment_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_assignments",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "division_work_area_team_assignments"
        ordering = [
            "work_area__division__engagement__client__client_name",
            "work_area__division__engagement__fiscal_year__fy_no",
            "work_area__division__engagement__service__service_desc",
            "work_area__division__division_name",
            "work_area__work_area_name",
            "team_member__first_name",
            "team_member__last_name",
            "team_member__code",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["work_area", "team_member"],
                name="uq_division_work_area_team_assignment",
            )
        ]

    def __str__(self):
        return f"{self.work_area} | {self.team_member}"
