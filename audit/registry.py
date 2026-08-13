"""Business models that produce audit entries (updates and deletes). Excludes auth/admin-only models."""

from __future__ import annotations

from collections.abc import Iterable

from config.models import ChartOfAccount
from engagements.models import (
    Engagement,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    EngagementDocumentationMapAttachment,
    EngagementTeamAssignment,
    DivisionWorkArea,
    DivisionWorkAreaPeriod,
    EngagementSchedule,
    EngagementWorkArea,
    EngagementWorkAreaPeriod,
    ServiceEngagementChecklistItem,
    ServiceEngagementChecklistWorkArea,
)
from gl.fiscal_years.models import FiscalYear
from hr.grades.models import Grade
from hr.qualifications.models import Qualification
from hr.teams.models import (
    TeamMemberGradePeriod,
    TeamMember,
    TeamMemberQualificationPeriod,
    TeamMemberRollPeriod,
)
from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from sales.invoices.models import Invoice
from sales.services.models import Service


def get_audited_models() -> Iterable[type]:
    return (
        Client,
        ClientClassification,
        ChartOfAccount,
        Service,
        Invoice,
        FiscalYear,
        Grade,
        Qualification,
        Engagement,
        EngagementSchedule,
        EngagementDivision,
        EngagementDivisionDocumentationMap,
        EngagementDivisionTeamAssignment,
        EngagementDocumentation,
        EngagementDocumentationMap,
        EngagementDocumentationMapAttachment,
        EngagementTeamAssignment,
        DivisionWorkArea,
        DivisionWorkAreaPeriod,
        EngagementWorkArea,
        EngagementWorkAreaPeriod,
        ServiceEngagementChecklistWorkArea,
        ServiceEngagementChecklistItem,
        TeamMember,
        TeamMemberRollPeriod,
        TeamMemberQualificationPeriod,
        TeamMemberGradePeriod,
    )
