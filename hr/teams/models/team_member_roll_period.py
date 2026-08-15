from django.conf import settings
from django.db import models

from .team_member import TeamMember


class TeamMemberRollPeriod(models.Model):
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.CASCADE,
        related_name="roll_periods",
    )
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_team_member_roll_periods",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "team_member_roll_periods"
        ordering = ["-from_date", "-id"]

    def __str__(self):
        to_label = self.to_date.isoformat() if self.to_date else "Present"
        return f"{self.team_member.code}: {self.from_date.isoformat()} - {to_label}"
