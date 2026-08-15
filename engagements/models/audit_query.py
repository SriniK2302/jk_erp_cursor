from django.conf import settings
from django.db import models

from .division_work_area import DivisionWorkArea
from .engagement_work_area import EngagementWorkArea

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
