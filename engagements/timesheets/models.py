from django.conf import settings
from django.db import models

from hr.teams.models import TeamMember


TIME_SESSION_STATUS_OPEN = "open"
TIME_SESSION_STATUS_CLOSED = "closed"
TIME_SESSION_STATUS_ADJUSTED = "adjusted"

TIME_SESSION_CLOSE_SOURCE_USER_STOP = "user_stop"
TIME_SESSION_CLOSE_SOURCE_AUTO_SWITCH = "auto_switch"
TIME_SESSION_CLOSE_SOURCE_AUTO_DAY_CLOSE = "auto_day_close"
TIME_SESSION_CLOSE_SOURCE_ADMIN_FIX = "admin_fix"


class TimeSession(models.Model):
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.PROTECT,
        related_name="time_sessions",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="started_time_sessions",
    )
    engagement = models.ForeignKey(
        "engagements.Engagement",
        on_delete=models.CASCADE,
        related_name="time_sessions",
    )
    division = models.ForeignKey(
        "engagements.EngagementDivision",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="time_sessions",
    )
    engagement_work_area = models.ForeignKey(
        "engagements.EngagementWorkArea",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="time_sessions",
    )
    division_work_area = models.ForeignKey(
        "engagements.DivisionWorkArea",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="time_sessions",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            (TIME_SESSION_STATUS_OPEN, "Open"),
            (TIME_SESSION_STATUS_CLOSED, "Closed"),
            (TIME_SESSION_STATUS_ADJUSTED, "Adjusted"),
        ],
        default=TIME_SESSION_STATUS_OPEN,
    )
    close_source = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=[
            ("", "N/A"),
            (TIME_SESSION_CLOSE_SOURCE_USER_STOP, "User stop"),
            (TIME_SESSION_CLOSE_SOURCE_AUTO_SWITCH, "Auto switch"),
            (TIME_SESSION_CLOSE_SOURCE_AUTO_DAY_CLOSE, "Auto day close"),
            (TIME_SESSION_CLOSE_SOURCE_ADMIN_FIX, "Admin fix"),
        ],
    )
    notes = models.TextField(blank=True, default="")
    task_description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="What you are doing on this engagement/division/work area (free text).",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "time_sessions"
        ordering = ["-started_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(engagement_work_area__isnull=True)
                        | models.Q(division_work_area__isnull=True)
                    )
                ),
                name="ck_time_session_one_work_area_type",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(ended_at__gte=models.F("started_at")),
                name="ck_time_session_ended_after_started",
            ),
            models.UniqueConstraint(
                fields=["team_member"],
                condition=models.Q(ended_at__isnull=True),
                name="uq_time_session_one_open_per_member",
            ),
        ]

    def __str__(self):
        return f"{self.team_member} | {self.started_at.isoformat()}"
