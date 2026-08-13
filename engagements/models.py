import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from gl.fiscal_years.models import FiscalYear
from hr.teams.models import TeamMember
from sales.services.models import Service
class Engagement(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    engagement_mail_id = models.EmailField(max_length=254, blank=True, default="")
    additional_mail_ids = models.TextField(blank=True, default="")
    fee_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=(
            "Optional engagement-level fee (e.g. audit fee). "
            "Certification engagements may use per-certificate amounts later."
        ),
    )
    status = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagements",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagements"
        ordering = ["client__client_name", "fiscal_year__fy_no", "service__service_desc"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "fiscal_year", "service"],
                name="uq_engagement_client_fy_service",
            )
        ]

    def __str__(self):
        return f"{self.client.client_code}-{self.fiscal_year.fy_no}-{self.service.service_code}"


class EngagementSchedule(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    planned_start = models.DateField()
    planned_finish = models.DateField()
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_schedules",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_schedules"
        ordering = ["planned_start", "id"]

    def __str__(self):
        return (
            f"{self.engagement} | {self.planned_start.isoformat()} - "
            f"{self.planned_finish.isoformat()}"
        )


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


class EngagementDivision(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="divisions",
    )
    division_name = models.CharField(max_length=120)
    division_mail_ids = models.TextField(blank=True, default="")
    status = models.CharField(max_length=40, blank=True, default="")
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    closure_source = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_divisions",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_divisions"
        ordering = [
            "engagement__client__client_name",
            "engagement__fiscal_year__fy_no",
            "engagement__service__service_desc",
            "division_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "division_name"],
                name="uq_engagement_division_name",
            )
        ]

    def __str__(self):
        return f"{self.engagement} | {self.division_name}"


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


class WorkAreaBase(models.Model):
    """Shared fields for engagement-level vs division-level work areas."""

    work_area_name = models.CharField(max_length=150)
    sort_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=40, blank=True, default="")
    closure_source = models.CharField(max_length=40, blank=True, default="")
    monetary_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional monetary amount for this work area (from work area notes).",
    )
    monetary_amount_unit = models.CharField(
        max_length=20,
        blank=True,
        default="lakhs",
        help_text="Unit for monetary_amount (lakhs, rs, crores).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.work_area_name


class EngagementWorkArea(WorkAreaBase):
    """Work area scoped to the whole engagement (no division)."""

    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="work_areas",
    )
    service_checklist_work_area = models.ForeignKey(
        "ServiceEngagementChecklistWorkArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="engagement_work_area_instances",
        help_text=(
            "Optional link to the Service engagement checklist work-area template "
            "(setup) used when this row was picked there—convenience for that pointer "
            "only; cleared if that template is deleted. Other masters are unrelated."
        ),
    )
    documentation = models.ForeignKey(
        "EngagementDocumentation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="engagement_work_areas",
        help_text="Broader documentation this work area falls under.",
    )

    class Meta:
        db_table = "engagement_work_areas"
        ordering = ["sort_order", "work_area_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "work_area_name"],
                name="uq_engagement_work_area_name",
            ),
            models.UniqueConstraint(
                fields=["engagement", "service_checklist_work_area"],
                condition=models.Q(service_checklist_work_area__isnull=False),
                name="uq_engagement_work_area_service_template",
            ),
        ]

    def __str__(self):
        return f"{self.engagement} | {self.work_area_name}"


class EngagementWorkAreaTeamAssignment(models.Model):
    work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    team_member = models.ForeignKey(
        TeamMember,
        on_delete=models.PROTECT,
        related_name="engagement_work_area_assignments",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    assignment_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_work_area_assignments",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_work_area_team_assignments"
        ordering = [
            "work_area__engagement__client__client_name",
            "work_area__engagement__fiscal_year__fy_no",
            "work_area__engagement__service__service_desc",
            "work_area__work_area_name",
            "team_member__first_name",
            "team_member__last_name",
            "team_member__code",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["work_area", "team_member"],
                name="uq_engagement_work_area_team_assignment",
            )
        ]

    def __str__(self):
        return f"{self.work_area} | {self.team_member}"


class DivisionWorkArea(WorkAreaBase):
    """Work area scoped to a single engagement division."""

    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="work_areas",
    )
    service_checklist_work_area = models.ForeignKey(
        "ServiceEngagementChecklistWorkArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="division_work_area_instances",
        help_text=(
            "Optional link to the Service engagement checklist work-area template "
            "(setup) used when this row was picked there—convenience for that pointer "
            "only; cleared if that template is deleted. Other masters are unrelated."
        ),
    )
    documentation = models.ForeignKey(
        "EngagementDocumentation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="division_work_areas",
        help_text="Broader documentation this work area falls under.",
    )

    class Meta:
        db_table = "division_work_areas"
        ordering = ["sort_order", "work_area_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["division", "work_area_name"],
                name="uq_division_work_area_name",
            ),
            models.UniqueConstraint(
                fields=["division", "service_checklist_work_area"],
                condition=models.Q(service_checklist_work_area__isnull=False),
                name="uq_division_work_area_service_template",
            ),
        ]

    def __str__(self):
        return f"{self.division} | {self.work_area_name}"


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


class DivisionWorkAreaStatusRemark(models.Model):
    """Standalone status remarks for a division work area."""

    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "division_work_area_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.work_area_id} | {self.created_on.isoformat()}"


class EngagementStatusRemark(models.Model):
    """Status remarks captured at engagement level."""

    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)


class EngagementDivisionStatusRemark(models.Model):
    """Status remarks captured at engagement division level."""

    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_division_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_division_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)


class EngagementWorkAreaStatusRemark(models.Model):
    """Status remarks captured at engagement work area level."""

    work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        related_name="status_remarks",
    )
    remark_date = models.DateField()
    remarks = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_work_area_status_remarks",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_work_area_status_remarks"
        ordering = ["-remark_date", "-created_on", "-id"]

    def save(self, *args, **kwargs):
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)


class AuditQuery(models.Model):
    """Raised query tracked against one work area."""

    ENTRY_TYPE_QUERY = "query"
    ENTRY_TYPE_REMARK = "remark"
    ENTRY_TYPE_CHOICES = [
        (ENTRY_TYPE_QUERY, "Query"),
        (ENTRY_TYPE_REMARK, "Remark"),
    ]
    RESPONDER_INTERNAL = "internal"
    RESPONDER_CLIENT = "client"
    RESPONDER_TYPE_CHOICES = [
        (RESPONDER_INTERNAL, "Internal"),
        (RESPONDER_CLIENT, "Client"),
    ]
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]
    AMOUNT_UNIT_LAKHS = "lakhs"
    AMOUNT_UNIT_RS = "rs"
    AMOUNT_UNIT_CRORES = "crores"
    AMOUNT_UNIT_CHOICES = [
        (AMOUNT_UNIT_CRORES, "Crores"),
        (AMOUNT_UNIT_LAKHS, "Lakhs"),
        (AMOUNT_UNIT_RS, "Rs"),
    ]

    engagement_work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_queries",
    )
    division_work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_queries",
    )
    service_checklist_item = models.ForeignKey(
        "ServiceEngagementChecklistItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_queries",
    )
    query_date = models.DateField()
    entry_type = models.CharField(
        max_length=20, choices=ENTRY_TYPE_CHOICES, default=ENTRY_TYPE_QUERY
    )
    subject = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount_unit = models.CharField(
        max_length=20, choices=AMOUNT_UNIT_CHOICES, default=AMOUNT_UNIT_LAKHS
    )
    query_text = models.TextField()
    response_expected_from = models.CharField(
        max_length=20,
        choices=RESPONDER_TYPE_CHOICES,
        default=RESPONDER_INTERNAL,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    working_paper_no = models.CharField(max_length=40, blank=True, default="")
    converted_to_working_paper = models.BooleanField(default=False)
    converted_on = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_audit_queries",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "audit_queries"
        ordering = ["-query_date", "-id"]

    def save(self, *args, **kwargs):
        self.subject = (self.subject or "").strip()
        self.query_text = (self.query_text or "").strip()
        super().save(*args, **kwargs)


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


def _audit_query_attachment_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    qid = instance.query_id
    query = instance.query
    if query.engagement_work_area_id:
        eid = query.engagement_work_area.engagement_id
        wid = query.engagement_work_area_id
        return f"audit_query_attachments/engagement/{eid}/{wid}/{qid}/{unique}"
    did = query.division_work_area.division_id
    wid = query.division_work_area_id
    return f"audit_query_attachments/division/{did}/{wid}/{qid}/{unique}"


class AuditQueryAttachment(models.Model):
    query = models.ForeignKey(
        AuditQuery,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_audit_query_attachment_upload_to)
    original_filename = models.CharField(max_length=255)
    document_reference_no = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_audit_query_attachments",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_query_attachments"
        ordering = ["-created_on", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.document_reference_no = (self.document_reference_no or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


@receiver(post_delete, sender=AuditQueryAttachment)
def _delete_audit_query_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


class EngagementWorkAreaPeriod(models.Model):
    """One planned/actual window for an engagement-level work area."""

    work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        related_name="schedule_rows",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    closure_source = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_work_area_schedule_rows",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_work_area_periods"
        ordering = ["planned_start", "id"]
        verbose_name = "Engagement work area schedule row"
        verbose_name_plural = "Engagement work area schedule rows"

    def __str__(self):
        planned_start = self.planned_start.isoformat() if self.planned_start else "—"
        planned_finish = self.planned_finish.isoformat() if self.planned_finish else "—"
        return (
            f"{self.work_area.work_area_name} | "
            f"{planned_start}–{planned_finish}"
        )


class DivisionWorkAreaPeriod(models.Model):
    """One planned/actual window for a division-level work area."""

    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="schedule_rows",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_finish = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_finish = models.DateField(null=True, blank=True)
    closure_source = models.CharField(max_length=40, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_schedule_rows",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "division_work_area_periods"
        ordering = ["planned_start", "id"]
        verbose_name = "Division work area schedule row"
        verbose_name_plural = "Division work area schedule rows"

    def __str__(self):
        planned_start = self.planned_start.isoformat() if self.planned_start else "—"
        planned_finish = self.planned_finish.isoformat() if self.planned_finish else "—"
        return (
            f"{self.work_area.work_area_name} | "
            f"{planned_start}–{planned_finish}"
        )


def _engagement_work_area_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    wid = instance.work_area_id
    eid = instance.work_area.engagement_id
    return f"engagement_work_area_documents/{eid}/{wid}/{unique}"


class EngagementWorkAreaDocument(models.Model):
    work_area = models.ForeignKey(
        EngagementWorkArea,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_date = models.DateField()
    description = models.CharField(max_length=255)
    document_reference_no = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    remarks = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=_engagement_work_area_document_upload_to)
    original_filename = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_work_area_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_work_area_documents"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        self.document_reference_no = (self.document_reference_no or "").strip()
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.work_area.work_area_name} | {self.original_filename}"


@receiver(post_delete, sender=EngagementWorkAreaDocument)
def _delete_engagement_work_area_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


def _division_work_area_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    wid = instance.work_area_id
    did = instance.work_area.division_id
    return f"division_work_area_documents/{did}/{wid}/{unique}"


class DivisionWorkAreaDocument(models.Model):
    work_area = models.ForeignKey(
        DivisionWorkArea,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_date = models.DateField()
    description = models.CharField(max_length=255)
    document_reference_no = models.CharField(
        max_length=100, blank=True, default="", db_index=True
    )
    remarks = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=_division_work_area_document_upload_to)
    original_filename = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_division_work_area_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "division_work_area_documents"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        self.document_reference_no = (self.document_reference_no or "").strip()
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.work_area.work_area_name} | {self.original_filename}"


@receiver(post_delete, sender=DivisionWorkAreaDocument)
def _delete_division_work_area_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


def _firm_reference_document_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "file"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"firm_reference_documents/{unique}"


class FirmReferenceDocument(models.Model):
    """Firm-wide reference file in Setup (not tied to documentation stage)."""

    DEFAULT_CATEGORY = "General / other"
    SUGGESTED_CATEGORIES = [
        "Audit methodology",
        "Tax",
        "IT & tools",
        "Firm policies",
        "Templates (non-client-specific)",
        "External standards & circulars",
        DEFAULT_CATEGORY,
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=100,
        default=DEFAULT_CATEGORY,
        db_index=True,
        help_text="Use a suggested name or type your own; this is shown in lists and search.",
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Comma-separated keywords for search (e.g. SA 230, sampling, Excel).",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive items stay in the database but are hidden from the default list.",
    )
    file = models.FileField(upload_to=_firm_reference_document_upload_to)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_firm_reference_documents",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "firm_reference_documents"
        ordering = ["category", "title", "pk"]

    def save(self, *args, **kwargs):
        self.title = (self.title or "").strip()
        self.category = (self.category or "").strip() or self.DEFAULT_CATEGORY
        self.description = (self.description or "").strip()
        self.tags = (self.tags or "").strip()
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            if "_" in base:
                prefix, sep, suffix = base.partition("_")
                if (
                    len(prefix) == 32
                    and sep == "_"
                    and all(c in "0123456789abcdef" for c in prefix.lower())
                ):
                    self.original_filename = (suffix or "file")[:255]
                else:
                    self.original_filename = (base or "file")[:255]
            else:
                self.original_filename = (base or "file")[:255]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


@receiver(post_delete, sender=FirmReferenceDocument)
def _delete_firm_reference_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


def _engagement_documentation_word_template_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "template"
    unique = f"{uuid.uuid4().hex}_{safe}"
    return f"engagement_documentation_templates/{unique}"


class EngagementDocumentation(models.Model):
    PRE_ENGAGEMENT = "pre_engagement"
    POST_ENGAGEMENT = "post_engagement"
    ENGAGEMENT_WORKING_PAPERS = "working_papers"
    ENGAGEMENT_PLANNING = "engagement_planning"
    ENGAGEMENT_CONCLUSION = "engagement_conclusion"
    DOCUMENT_STAGE_CHOICES = [
        (PRE_ENGAGEMENT, "Pre-engagement"),
        (POST_ENGAGEMENT, "Post-engagement"),
        (ENGAGEMENT_WORKING_PAPERS, "Engagement Working Papers"),
        (ENGAGEMENT_PLANNING, "Engagement Planning"),
        (ENGAGEMENT_CONCLUSION, "Engagement Conclusion"),
    ]

    standard_document = models.CharField(max_length=180)
    filled_download_label = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Optional short suffix for Fill Word downloads, after date · FY · client code · "
            "service code (e.g. MR 01). Leave blank to build a short name from the standard document."
        ),
    )
    word_template = models.FileField(
        upload_to=_engagement_documentation_word_template_upload_to,
        blank=True,
        null=True,
        help_text="Optional Word template (.doc or .docx) for this standard document.",
    )
    document_stage = models.CharField(max_length=30, choices=DOCUMENT_STAGE_CHOICES)
    applicable_classifications = models.ManyToManyField(
        ClientClassification,
        related_name="engagement_documentations",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentations",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_documentations"
        ordering = [
            "document_stage",
            "standard_document",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["standard_document", "document_stage"],
                name="uq_engagementdocumentation_standard_document_stage",
            )
        ]

    @property
    def is_mr02_catalog_item(self) -> bool:
        """Setup row uses MR 02 suffix (enables per-engagement MR 02 acknowledgment matrix)."""
        from engagements.documentations.representation_matrix import is_mr02_documentation

        return is_mr02_documentation(self)

    def word_template_display_name(self) -> str:
        """Uploaded filename for display (stored as ``{uuid32}_{original}``)."""
        if not self.word_template:
            return ""
        raw = getattr(self.word_template, "name", "") or ""
        base = raw.replace("\\", "/").rsplit("/", 1)[-1]
        if "_" in base:
            prefix, sep, suffix = base.partition("_")
            if (
                len(prefix) == 32
                and sep == "_"
                and all(c in "0123456789abcdef" for c in prefix.lower())
            ):
                return suffix or "template"
        return base or "template"

    def __str__(self):
        names = ", ".join(
            self.applicable_classifications.order_by(
                "classification_name"
            ).values_list("classification_name", flat=True)
        )
        label = names or "—"
        return f"{self.standard_document} ({self.get_document_stage_display()} — {label})"


@receiver(post_delete, sender=EngagementDocumentation)
def _delete_engagement_documentation_word_template_file(sender, instance, **kwargs):
    if instance.word_template:
        instance.word_template.delete(save=False)


class EngagementDocumentationMap(models.Model):
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.CASCADE,
        related_name="documentation_maps",
    )
    documentation = models.ForeignKey(
        EngagementDocumentation,
        on_delete=models.PROTECT,
        related_name="engagement_maps",
    )
    documentation_date = models.DateField(
        help_text="Date used to order mapped documentation (e.g. planned or signed date).",
    )
    representation_point_matrix = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-engagement acknowledgment matrix for MR 02 (and similar) items: "
            "point id → {status, notes?}. Empty when not used."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentation_maps",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_documentation_maps"
        ordering = [
            "documentation_date",
            "documentation__document_stage",
            "documentation__standard_document",
            "pk",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "documentation"],
                name="uq_engagement_documentation_map",
            )
        ]

    def __str__(self):
        return f"{self.engagement} | {self.documentation}"


def _engagement_documentation_map_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    mid = instance.documentation_map_id
    eid = instance.documentation_map.engagement_id
    return f"engagement_documentation/{eid}/{mid}/{unique}"


class EngagementDocumentationMapAttachment(models.Model):
    documentation_map = models.ForeignKey(
        EngagementDocumentationMap,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_engagement_documentation_map_upload_to)
    original_filename = models.CharField(max_length=255)
    document_date = models.DateField(
        help_text="Date of the underlying document (e.g. letter or signing date).",
    )
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_documentation_attachments",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_documentation_map_attachments"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


@receiver(post_delete, sender=EngagementDocumentationMapAttachment)
def _delete_engagement_documentation_map_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


class EngagementDivisionDocumentationMap(models.Model):
    division = models.ForeignKey(
        EngagementDivision,
        on_delete=models.CASCADE,
        related_name="documentation_maps",
    )
    documentation = models.ForeignKey(
        EngagementDocumentation,
        on_delete=models.PROTECT,
        related_name="division_maps",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_division_documentation_maps",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "engagement_division_documentation_maps"
        ordering = [
            "division__engagement__client__client_name",
            "division__engagement__fiscal_year__fy_no",
            "division__engagement__service__service_desc",
            "division__division_name",
            "documentation__document_stage",
            "documentation__standard_document",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["division", "documentation"],
                name="uq_engagement_division_documentation_map",
            )
        ]

    def __str__(self):
        return f"{self.division} | {self.documentation}"


def _engagement_division_documentation_map_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    mid = instance.documentation_map_id
    did = instance.documentation_map.division_id
    return f"engagement_division_documentation/{did}/{mid}/{unique}"


class EngagementDivisionDocumentationMapAttachment(models.Model):
    documentation_map = models.ForeignKey(
        EngagementDivisionDocumentationMap,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_engagement_division_documentation_map_upload_to)
    original_filename = models.CharField(max_length=255)
    document_date = models.DateField(
        help_text="Date of the underlying document (e.g. letter or signing date).",
    )
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_engagement_division_documentation_attachments",
    )
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "engagement_division_documentation_map_attachments"
        ordering = ["-document_date", "original_filename", "pk"]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            raw = getattr(self.file, "name", "") or ""
            base = raw.replace("\\", "/").rsplit("/", 1)[-1]
            self.original_filename = (base or "file")[:255]
        self.description = (self.description or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename


class ServiceEngagementChecklistWorkArea(models.Model):
    """
    Setup template: a named work area under a service, grouping engagement checklist
    line items the team should complete.
    """

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="engagement_checklist_work_areas",
    )
    name = models.CharField(max_length=200)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_service_engagement_checklist_work_areas",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagement_checklist_work_areas"
        ordering = ["service", "sort_order", "id"]

    def __str__(self):
        return f"{self.service.service_code} · {self.name}"


class ServiceEngagementChecklistItem(models.Model):
    """One actionable checklist line under a service work-area template."""

    work_area = models.ForeignKey(
        ServiceEngagementChecklistWorkArea,
        on_delete=models.CASCADE,
        related_name="items",
    )
    line_text = models.CharField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_service_engagement_checklist_items",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_engagement_checklist_items"
        ordering = ["work_area", "sort_order", "id"]

    def __str__(self):
        return self.line_text[:80]


@receiver(post_delete, sender=EngagementDivisionDocumentationMapAttachment)
def _delete_engagement_division_documentation_map_attachment_file(
    sender, instance, **kwargs
):
    if instance.file:
        instance.file.delete(save=False)


STATUS_PENDING = "Pending"
STATUS_SCHEDULED = "Scheduled"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED = "Completed"
CLOSURE_SOURCE_ENGAGEMENT_AUTO = "engagement_auto_close"


def _close_children_for_engagement(engagement_id, closed_on):
    if closed_on is None:
        return
    EngagementDivision.objects.filter(
        engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementWorkAreaPeriod.objects.filter(
        work_area__engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    DivisionWorkAreaPeriod.objects.filter(
        work_area__division__engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementDivision.objects.filter(engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementWorkArea.objects.filter(engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    DivisionWorkArea.objects.filter(division__engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )


def _apply_actual_start_for_engagement(engagement_id, started_on):
    if started_on is None:
        return
    EngagementDivision.objects.filter(
        engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)
    EngagementWorkAreaPeriod.objects.filter(
        work_area__engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)
    DivisionWorkAreaPeriod.objects.filter(
        work_area__division__engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)


def _set_engagement_status(engagement_id):
    engagement = Engagement.objects.filter(pk=engagement_id).first()
    if engagement is None:
        return
    has_actual_finish = engagement.schedules.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    else:
        has_docs = (
            EngagementDocumentationMapAttachment.objects.filter(
                documentation_map__engagement_id=engagement_id
            ).exists()
            or EngagementDivisionDocumentationMapAttachment.objects.filter(
                documentation_map__division__engagement_id=engagement_id
            ).exists()
            or EngagementWorkAreaDocument.objects.filter(
                work_area__engagement_id=engagement_id
            ).exists()
            or DivisionWorkAreaDocument.objects.filter(
                work_area__division__engagement_id=engagement_id
            ).exists()
        )
        if has_docs:
            next_status = STATUS_IN_PROGRESS
        elif engagement.schedules.filter(planned_finish__isnull=False).exists():
            next_status = STATUS_SCHEDULED
        else:
            next_status = STATUS_PENDING
    Engagement.objects.filter(pk=engagement_id).update(status=next_status)


def _set_division_status(division_id):
    division = EngagementDivision.objects.filter(pk=division_id).first()
    if division is None:
        return
    if division.actual_finish is not None:
        next_status = STATUS_COMPLETED
    else:
        has_docs = (
            EngagementDivisionDocumentationMapAttachment.objects.filter(
                documentation_map__division_id=division_id
            ).exists()
            or DivisionWorkAreaDocument.objects.filter(work_area__division_id=division_id).exists()
        )
        if has_docs:
            next_status = STATUS_IN_PROGRESS
        elif division.planned_finish is not None:
            next_status = STATUS_SCHEDULED
        else:
            next_status = STATUS_PENDING
    EngagementDivision.objects.filter(pk=division_id).update(status=next_status)


def _set_engagement_work_area_status(work_area_id):
    work_area = EngagementWorkArea.objects.filter(pk=work_area_id).first()
    if work_area is None:
        return
    has_actual_finish = work_area.schedule_rows.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    elif work_area.documents.exists():
        next_status = STATUS_IN_PROGRESS
    elif work_area.schedule_rows.filter(planned_finish__isnull=False).exists():
        next_status = STATUS_SCHEDULED
    else:
        next_status = STATUS_PENDING
    EngagementWorkArea.objects.filter(pk=work_area_id).update(status=next_status)


def _set_division_work_area_status(work_area_id):
    work_area = DivisionWorkArea.objects.filter(pk=work_area_id).first()
    if work_area is None:
        return
    has_actual_finish = work_area.schedule_rows.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    elif work_area.documents.exists():
        next_status = STATUS_IN_PROGRESS
    elif work_area.schedule_rows.filter(planned_finish__isnull=False).exists():
        next_status = STATUS_SCHEDULED
    else:
        next_status = STATUS_PENDING
    DivisionWorkArea.objects.filter(pk=work_area_id).update(status=next_status)


@receiver(post_save, sender=Engagement)
def _engagement_status_on_save(sender, instance, **kwargs):
    _set_engagement_status(instance.pk)


@receiver(post_save, sender=EngagementSchedule)
@receiver(post_delete, sender=EngagementSchedule)
def _engagement_status_on_schedule_change(sender, instance, **kwargs):
    completed_on = (
        EngagementSchedule.objects.filter(
            engagement_id=instance.engagement_id,
            actual_finish__isnull=False,
        )
        .order_by("-actual_finish")
        .values_list("actual_finish", flat=True)
        .first()
    )
    started_on = None
    if completed_on is not None:
        started_on = (
            EngagementSchedule.objects.filter(
                engagement_id=instance.engagement_id,
                actual_start__isnull=False,
            )
            .order_by("actual_start")
            .values_list("actual_start", flat=True)
            .first()
        )
    _apply_actual_start_for_engagement(instance.engagement_id, started_on)
    _close_children_for_engagement(instance.engagement_id, completed_on)
    _set_engagement_status(instance.engagement_id)


@receiver(post_save, sender=EngagementDocumentationMapAttachment)
@receiver(post_delete, sender=EngagementDocumentationMapAttachment)
def _engagement_status_on_engagement_doc_change(sender, instance, **kwargs):
    _set_engagement_status(instance.documentation_map.engagement_id)


@receiver(post_save, sender=EngagementDivisionDocumentationMapAttachment)
@receiver(post_delete, sender=EngagementDivisionDocumentationMapAttachment)
def _status_on_division_doc_change(sender, instance, **kwargs):
    division_id = instance.documentation_map.division_id
    _set_division_status(division_id)
    _set_engagement_status(instance.documentation_map.division.engagement_id)


@receiver(post_save, sender=EngagementWorkAreaDocument)
@receiver(post_delete, sender=EngagementWorkAreaDocument)
def _status_on_engagement_work_area_doc_change(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.work_area_id)
    _set_engagement_status(instance.work_area.engagement_id)


@receiver(post_save, sender=DivisionWorkAreaDocument)
@receiver(post_delete, sender=DivisionWorkAreaDocument)
def _status_on_division_work_area_doc_change(sender, instance, **kwargs):
    _set_division_work_area_status(instance.work_area_id)
    _set_division_status(instance.work_area.division_id)
    _set_engagement_status(instance.work_area.division.engagement_id)


@receiver(post_save, sender=EngagementDivision)
def _division_status_on_save(sender, instance, **kwargs):
    _set_division_status(instance.pk)


@receiver(post_save, sender=EngagementWorkArea)
def _engagement_work_area_status_on_save(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.pk)


@receiver(post_save, sender=DivisionWorkArea)
def _division_work_area_status_on_save(sender, instance, **kwargs):
    _set_division_work_area_status(instance.pk)


@receiver(post_save, sender=EngagementWorkAreaPeriod)
@receiver(post_delete, sender=EngagementWorkAreaPeriod)
def _engagement_work_area_status_on_period_change(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.work_area_id)


@receiver(post_save, sender=DivisionWorkAreaPeriod)
@receiver(post_delete, sender=DivisionWorkAreaPeriod)
def _division_work_area_status_on_period_change(sender, instance, **kwargs):
    _set_division_work_area_status(instance.work_area_id)

# Unified work-document model (see engagements/work_documents/models.py)
from engagements.work_documents.models import WorkDocument  # noqa: E402,F401
