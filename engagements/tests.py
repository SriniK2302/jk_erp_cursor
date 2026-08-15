import io
import json
import shutil
import tempfile
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.models import SmtpMailSettings
from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from gl.fiscal_years.models import FiscalYear
from hr.grades.models import Grade
from hr.teams.models import TeamMember, TeamMemberGradePeriod, TeamMemberRollPeriod
from sales.services.models import Service
from engagements.documentations.forms import EngagementDocumentationForm

from .forms import (
    DivisionWorkAreaPeriodForm,
    DivisionWorkAreaTeamAssignmentForm,
    EngagementDivisionForm,
    EngagementDivisionTeamAssignmentForm,
    EngagementDivisionDocumentationMapForm,
    EngagementDocumentationMapForm,
    EngagementForm,
    EngagementScheduleForm,
    EngagementTeamAssignmentForm,
    DivisionWorkAreaForm,
    EngagementWorkAreaForm,
    EngagementWorkAreaPeriodForm,
)
from .models import (
    AuditQuery,
    AuditQueryAttachment,
    AuditQueryMailDraftLog,
    DivisionWorkAreaConfirmationMailLog,
    DivisionWorkAreaPeriod,
    DivisionWorkAreaStatusRemark,
    Engagement,
    EngagementDivisionStatusRemark,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDivisionDocumentationMapAttachment,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    EngagementDocumentationMapAttachment,
    EngagementTeamAssignment,
    FirmReferenceDocument,
    DivisionWorkArea,
    DivisionWorkAreaDocument,
    DivisionWorkAreaTeamAssignment,
    EngagementSchedule,
    EngagementStatusRemark,
    EngagementWorkArea,
    EngagementWorkAreaPeriod,
    EngagementWorkAreaStatusRemark,
    EngagementWorkAreaDocument,
    EngagementWorkAreaTeamAssignment,
    ServiceEngagementChecklistItem,
    ServiceEngagementChecklistWorkArea,
)
from .timesheets.models import TIME_SESSION_STATUS_CLOSED, TimeSession
from .work_area_notes_batch import (
    checklist_items_payload,
    checklist_items_queryset,
    resolve_service_checklist_template,
    work_area_has_checklist_template,
)


def grant_engagements_module_access(user):
    group, _ = Group.objects.get_or_create(name="module_engagements")
    user.groups.add(group)
    return group


def assign_user_to_engagement(user, engagement, *, created_by=None):
    """Grant module access and a team assignment so engagement-scoped views return 200."""
    grant_engagements_module_access(user)
    created_by = created_by or user
    code = f"U{user.pk}"[-4:].rjust(4, "0")
    member, _ = TeamMember.objects.get_or_create(
        user=user,
        defaults={
            "first_name": "Test",
            "last_name": "Member",
            "called_as": f"TM{user.pk}",
            "code": code,
            "created_by": created_by,
        },
    )
    EngagementTeamAssignment.objects.get_or_create(
        engagement=engagement,
        team_member=member,
        defaults={
            "planned_start": date(2000, 1, 1),
            "planned_finish": date(2000, 12, 31),
            "created_by": created_by,
        },
    )
    return member


class ChecklistItemsPayloadTests(TestCase):
    def test_payload_trims_line_text(self):
        class _Obj:
            pk = 7
            line_text = "  Line A  \n"

        self.assertEqual(
            checklist_items_payload([_Obj()]),
            [{"id": 7, "text": "Line A"}],
        )

    def test_payload_empty(self):
        self.assertEqual(checklist_items_payload([]), [])


class ResolveServiceChecklistTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="resolve_tpl_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Resolve Tpl Corp",
            client_short_name="RTC",
            client_code="RTC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY48",
            start_date=date(2047, 4, 1),
            end_date=date(2048, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="SAUD",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Unit I",
            created_by=self.user,
        )
        self.tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Property, Plan and Equipment",
            sort_order=0,
            created_by=self.user,
        )
        ServiceEngagementChecklistItem.objects.create(
            work_area=self.tpl,
            line_text="Verify FA register",
            sort_order=0,
            created_by=self.user,
        )

    def test_resolves_template_by_work_area_name_when_fk_not_set(self):
        work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Property, Plan and Equipment",
            sort_order=1,
            created_by=self.user,
        )
        self.assertIsNone(work_area.service_checklist_work_area_id)
        resolved = resolve_service_checklist_template(work_area)
        self.assertEqual(resolved.pk, self.tpl.pk)
        self.assertTrue(work_area_has_checklist_template(work_area))
        self.assertEqual(checklist_items_queryset(work_area).count(), 1)


class EngagementScheduleFormTests(TestCase):
    def test_planned_finish_cannot_be_before_planned_start(self):
        form = EngagementScheduleForm(
            data={
                "planned_start": date(2026, 4, 10),
                "planned_finish": date(2026, 4, 5),
                "actual_start": "",
                "actual_finish": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_finish", form.errors)


class EngagementFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Acme Corp",
            client_short_name="Acme",
            client_code="ACME",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUDT",
            created_by=self.user,
        )

    def test_unique_client_fy_service_combination(self):
        Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        form = EngagementForm(
            data={
                "client": self.client_item.pk,
                "fiscal_year": self.fy.pk,
                "service": self.service.pk,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_fee_amount_parses_comma_formatted_input(self):
        from decimal import Decimal

        form = EngagementForm(
            data={
                "client": self.client_item.pk,
                "fiscal_year": self.fy.pk,
                "service": self.service.pk,
                "fee_amount": "85,000",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fee_amount"], Decimal("85000"))

    def test_fee_amount_rejects_invalid_input(self):
        form = EngagementForm(
            data={
                "client": self.client_item.pk,
                "fiscal_year": self.fy.pk,
                "service": self.service.pk,
                "fee_amount": "not-a-number",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fee_amount", form.errors)

    def test_duplicate_client_fy_service_shows_clear_error(self):
        Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        form = EngagementForm(
            data={
                "client": self.client_item.pk,
                "fiscal_year": self.fy.pk,
                "service": self.service.pk,
                "fee_amount": "1,000",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "An engagement already exists for this client, FY, and service.",
            form.errors.get("__all__", []),
        )


class EngagementTeamAssignmentFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_team_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Team Assign Corp",
            client_short_name="TAC",
            client_code="TAC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY36",
            start_date=date(2035, 4, 1),
            end_date=date(2036, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Assurance",
            service_code="ASUR",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2035, 4, 10),
            planned_finish=date(2035, 4, 25),
            created_by=self.user,
        )
        self.member = TeamMember.objects.create(
            first_name="Anu",
            last_name="Rao",
            called_as="Anu",
            code="AR01",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2035, 4, 1),
            to_date=None,
            notes="Joined",
            created_by=self.user,
        )

    def test_prefills_planned_dates_from_engagement_schedule(self):
        form = EngagementTeamAssignmentForm(engagement=self.engagement)
        self.assertEqual(form.initial.get("planned_start"), date(2035, 4, 10))
        self.assertEqual(form.initial.get("planned_finish"), date(2035, 4, 25))

    def test_rejects_assignment_dates_outside_engagement_schedule_window(self):
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2035, 4, 1),
                "planned_finish": date(2035, 4, 30),
            },
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)
        self.assertIn("planned_finish", form.errors)

    def test_allows_multiple_date_ranges_for_same_team_member(self):
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2035, 4, 10),
            planned_finish=date(2035, 4, 14),
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2035, 4, 18),
                "planned_finish": date(2035, 4, 22),
            },
            engagement=self.engagement,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_overlapping_date_ranges_for_same_team_member(self):
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2035, 4, 10),
            planned_finish=date(2035, 4, 18),
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2035, 4, 15),
                "planned_finish": date(2035, 4, 22),
            },
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)

    def test_allows_adjacent_non_overlapping_ranges_same_team_member(self):
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2035, 4, 10),
            planned_finish=date(2035, 4, 14),
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2035, 4, 15),
                "planned_finish": date(2035, 4, 20),
            },
            engagement=self.engagement,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_dates_outside_team_roll_period(self):
        later_joiner = TeamMember.objects.create(
            first_name="Sorna",
            last_name="Lakshmi",
            called_as="Sorna",
            code="SL01",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=later_joiner,
            from_date=date(2035, 4, 20),
            to_date=None,
            notes="Joined later",
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": later_joiner.pk,
                "planned_start": date(2035, 4, 10),
                "planned_finish": date(2035, 4, 22),
            },
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)

    def test_allows_assignment_when_later_grade_period_covers_dates(self):
        EngagementSchedule.objects.filter(engagement=self.engagement).update(
            planned_finish=date(2035, 6, 30),
        )
        grade_old = Grade.objects.create(
            grade_desc="Associate",
            grade_code="ASC1",
            created_by=self.user,
        )
        grade_new = Grade.objects.create(
            grade_desc="Manager",
            grade_code="MGR1",
            created_by=self.user,
        )
        member = TeamMember.objects.create(
            first_name="Vishnu",
            last_name="Prasath",
            called_as="Vishnu",
            code="PE04",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=member,
            from_date=date(2035, 1, 20),
            to_date=date(2035, 4, 30),
            notes="",
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=member,
            grade=grade_old,
            from_date=date(2035, 1, 20),
            to_date=date(2035, 4, 30),
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=member,
            grade=grade_new,
            from_date=date(2035, 5, 1),
            to_date=None,
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": member.pk,
                "planned_start": date(2035, 6, 1),
                "planned_finish": date(2035, 6, 13),
            },
            engagement=self.engagement,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_assignment_in_gap_between_grade_periods(self):
        grade = Grade.objects.create(
            grade_desc="Associate",
            grade_code="ASC2",
            created_by=self.user,
        )
        member = TeamMember.objects.create(
            first_name="Gap",
            last_name="Member",
            called_as="Gap",
            code="GAP1",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=member,
            from_date=date(2035, 4, 1),
            to_date=None,
            notes="",
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=member,
            grade=grade,
            from_date=date(2035, 4, 1),
            to_date=date(2035, 4, 14),
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=member,
            grade=grade,
            from_date=date(2035, 4, 20),
            to_date=None,
            created_by=self.user,
        )
        form = EngagementTeamAssignmentForm(
            data={
                "team_member": member.pk,
                "planned_start": date(2035, 4, 15),
                "planned_finish": date(2035, 4, 18),
            },
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)


class EngagementDivisionTeamAssignmentFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_div_team_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Division Team Corp",
            client_short_name="DTC",
            client_code="DTC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY37",
            start_date=date(2036, 4, 1),
            end_date=date(2037, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Internal Audit",
            service_code="IADT",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2036, 4, 10),
            planned_finish=date(2036, 5, 10),
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Branch A",
            planned_start=date(2036, 4, 15),
            planned_finish=date(2036, 5, 5),
            created_by=self.user,
        )
        self.member = TeamMember.objects.create(
            first_name="Vikram",
            last_name="Das",
            called_as="Vik",
            code="VD01",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2036, 4, 1),
            to_date=None,
            notes="Joined",
            created_by=self.user,
        )

    def test_prefills_planned_dates_from_division_window(self):
        form = EngagementDivisionTeamAssignmentForm(division=self.division)
        self.assertEqual(form.initial.get("planned_start"), date(2036, 4, 15))
        self.assertEqual(form.initial.get("planned_finish"), date(2036, 5, 5))

    def test_rejects_assignment_dates_outside_division_window(self):
        form = EngagementDivisionTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2036, 4, 12),
                "planned_finish": date(2036, 5, 8),
            },
            division=self.division,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)
        self.assertIn("planned_finish", form.errors)

    def test_allows_multiple_date_ranges_for_same_team_member(self):
        EngagementDivisionTeamAssignment.objects.create(
            division=self.division,
            team_member=self.member,
            planned_start=date(2036, 4, 15),
            planned_finish=date(2036, 4, 22),
            created_by=self.user,
        )
        form = EngagementDivisionTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2036, 4, 25),
                "planned_finish": date(2036, 5, 4),
            },
            division=self.division,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_overlapping_date_ranges_for_same_team_member(self):
        EngagementDivisionTeamAssignment.objects.create(
            division=self.division,
            team_member=self.member,
            planned_start=date(2036, 4, 15),
            planned_finish=date(2036, 4, 25),
            created_by=self.user,
        )
        form = EngagementDivisionTeamAssignmentForm(
            data={
                "team_member": self.member.pk,
                "planned_start": date(2036, 4, 20),
                "planned_finish": date(2036, 5, 2),
            },
            division=self.division,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)

    def test_rejects_dates_outside_team_roll_period(self):
        later_joiner = TeamMember.objects.create(
            first_name="Sorna",
            last_name="Lakshmi",
            called_as="Sorna",
            code="SL02",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=later_joiner,
            from_date=date(2036, 4, 20),
            to_date=None,
            notes="Joined later",
            created_by=self.user,
        )
        form = EngagementDivisionTeamAssignmentForm(
            data={
                "team_member": later_joiner.pk,
                "planned_start": date(2036, 4, 15),
                "planned_finish": date(2036, 4, 25),
            },
            division=self.division,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)


class EngagementDivisionFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_div_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Blue Corp",
            client_short_name="Blue",
            client_code="BLUC",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Tax",
            service_code="TAX1",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )

    def test_engagement_field_shows_client_fy_service_not_internal_code(self):
        form = EngagementDivisionForm()
        label = form.fields["engagement"].label_from_instance(self.engagement)
        self.assertEqual(label, "Blue · FY27 · Tax")
        self.assertNotIn("BLUC", label)
        self.assertNotIn("TAX1", label)

    def test_division_name_is_trimmed(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 1),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "  Statutory Audit  ",
                "planned_start": date(2026, 4, 2),
                "planned_finish": date(2026, 4, 25),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["division_name"], "Statutory Audit")

    def test_unique_division_per_engagement(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 1),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Consulting",
            planned_start=date(2026, 4, 5),
            planned_finish=date(2026, 4, 20),
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Consulting",
                "planned_start": date(2026, 4, 6),
                "planned_finish": date(2026, 4, 21),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_planned_start_cannot_be_before_earliest_engagement_planned_start(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 10),
            planned_finish=date(2026, 4, 20),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 5),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Branch A",
                "planned_start": date(2026, 4, 1),
                "planned_finish": date(2026, 4, 29),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)

    def test_planned_finish_cannot_be_after_latest_engagement_planned_finish(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 10),
            planned_finish=date(2026, 4, 20),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 5),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Branch B",
                "planned_start": date(2026, 4, 6),
                "planned_finish": date(2026, 5, 1),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_finish", form.errors)

    def test_planned_start_may_be_blank_when_finish_within_engagement_window(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 1),
            planned_finish=date(2026, 5, 31),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Ramco USA",
                "planned_start": "",
                "planned_finish": date(2026, 5, 16),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_both_division_planned_dates_may_be_blank(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 1),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Shell division",
                "planned_start": "",
                "planned_finish": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_division_without_planned_dates_valid_even_without_engagement_schedule(self):
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Intake before schedule",
                "planned_start": "",
                "planned_finish": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_finish_only_cannot_be_before_engagement_earliest(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 10),
            planned_finish=date(2026, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        form = EngagementDivisionForm(
            data={
                "engagement": self.engagement.pk,
                "division_name": "Early finish only",
                "planned_start": "",
                "planned_finish": date(2026, 4, 5),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("planned_finish", form.errors)


class EngagementScheduleBoundsJsonTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_user(
            username="bounds_su",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.other = get_user_model().objects.create_user(
            username="bounds_other",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="BoundsCo",
            defaults={"created_by": self.superuser},
        )
        self.client_item = Client.objects.create(
            client_name="Bounds Client",
            client_short_name="Bounds",
            client_code="BNDS",
            classification=self.classification,
            is_active=True,
            created_by=self.superuser,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY99",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.superuser,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUD9",
            created_by=self.superuser,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.superuser,
        )

    def test_returns_earliest_and_latest_across_schedule_rows(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 10),
            planned_finish=date(2026, 4, 20),
            created_by=self.superuser,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2026, 4, 5),
            planned_finish=date(2026, 4, 30),
            created_by=self.superuser,
        )
        self.client.login(username="bounds_su", password="pass12345")
        url = reverse(
            "engagement_schedule_bounds",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["planned_start"], "2026-04-05")
        self.assertEqual(data["planned_finish"], "2026-04-30")

    def test_returns_nulls_when_no_schedule_rows(self):
        self.client.login(username="bounds_su", password="pass12345")
        url = reverse(
            "engagement_schedule_bounds",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIsNone(data["planned_start"])
        self.assertIsNone(data["planned_finish"])

    def test_user_without_engagement_access_gets_404(self):
        self.client.login(username="bounds_other", password="pass12345")
        url = reverse(
            "engagement_schedule_bounds",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class EngagementDocumentationFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_doc_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Private Limited Company",
            defaults={"created_by": self.user},
        )

    def test_standard_document_is_trimmed(self):
        form = EngagementDocumentationForm(
            data={
                "standard_document": "  Engagement Letter  ",
                "document_stage": EngagementDocumentation.PRE_ENGAGEMENT,
                "applicable_classifications": [str(self.classification.pk)],
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["standard_document"], "Engagement Letter")

    def test_applicable_classifications_required(self):
        form = EngagementDocumentationForm(
            data={
                "standard_document": "Completion Memo",
                "document_stage": EngagementDocumentation.POST_ENGAGEMENT,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("applicable_classifications", form.errors)

    def test_engagement_working_papers_stage_is_accepted(self):
        form = EngagementDocumentationForm(
            data={
                "standard_document": "Evidence File",
                "document_stage": EngagementDocumentation.ENGAGEMENT_WORKING_PAPERS,
                "applicable_classifications": [str(self.classification.pk)],
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_engagement_planning_and_conclusion_stages_are_accepted(self):
        for stage in (
            EngagementDocumentation.ENGAGEMENT_PLANNING,
            EngagementDocumentation.ENGAGEMENT_CONCLUSION,
        ):
            with self.subTest(stage=stage):
                form = EngagementDocumentationForm(
                    data={
                        "standard_document": "Sample doc",
                        "document_stage": stage,
                        "applicable_classifications": [str(self.classification.pk)],
                    }
                )
                self.assertTrue(form.is_valid(), form.errors)

    def test_word_template_rejects_non_word_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("notes.pdf", b"%PDF-1.4", content_type="application/pdf")
        form = EngagementDocumentationForm(
            data={
                "standard_document": "Trial balance",
                "document_stage": EngagementDocumentation.PRE_ENGAGEMENT,
                "applicable_classifications": [str(self.classification.pk)],
            },
            files={"word_template": bad},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("word_template", form.errors)

    def test_word_template_accepts_docx_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile(
            "master.docx",
            b"PK\x03\x04fake",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        form = EngagementDocumentationForm(
            data={
                "standard_document": "Management letter",
                "document_stage": EngagementDocumentation.POST_ENGAGEMENT,
                "applicable_classifications": [str(self.classification.pk)],
            },
            files={"word_template": f},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_word_template_display_name_strips_uuid_storage_prefix(self):
        doc = EngagementDocumentation()
        doc.word_template = type("F", (), {"name": "engagement_documentation_templates/" + "a" * 32 + "_My Report.docx"})()
        self.assertEqual(doc.word_template_display_name, "My Report.docx")

    def test_delete_word_template_form_action_clears_file(self):
        media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=media):
                doc = EngagementDocumentation.objects.create(
                    standard_document="With template",
                    document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
                    created_by=self.user,
                )
                doc.applicable_classifications.add(self.classification)
                doc.word_template.save(
                    "upload.docx",
                    SimpleUploadedFile(
                        "upload.docx",
                        b"PK\x03\x04",
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                    save=True,
                )
                self.client.force_login(self.user)
                edit_url = reverse(
                    "engagement_documentation_edit", kwargs={"pk": doc.pk}
                )
                response = self.client.post(
                    edit_url, {"form_action": "delete_word_template"}
                )
                self.assertEqual(response.status_code, 302)
                doc.refresh_from_db()
                self.assertFalse(doc.word_template)
        finally:
            shutil.rmtree(media, ignore_errors=True)


class ReferenceDocumentsPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ref_docs_user",
            password="pass12345",
        )

    def test_reference_documents_get_ok_when_logged_in(self):
        self.client.force_login(self.user)
        url = reverse("reference_documents")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reference documents")

    def test_reference_documents_search_across_fields(self):
        FirmReferenceDocument.objects.create(
            title="Tax memo",
            category="Tax",
            file=SimpleUploadedFile("a.txt", b"x", content_type="text/plain"),
            original_filename="a.txt",
            created_by=self.user,
        )
        FirmReferenceDocument.objects.create(
            title="Audit guide",
            category="Audit methodology",
            file=SimpleUploadedFile("b.txt", b"y", content_type="text/plain"),
            original_filename="b.txt",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse("reference_documents")
        response = self.client.get(url, {"q": "memo"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tax memo")
        self.assertNotContains(response, "Audit guide")

    def test_reference_documents_search_matches_category_label(self):
        FirmReferenceDocument.objects.create(
            title="Spreadsheet pack",
            category="IT & tools",
            file=SimpleUploadedFile("c.txt", b"z", content_type="text/plain"),
            original_filename="c.txt",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse("reference_documents")
        response = self.client.get(url, {"q": "IT & tools"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spreadsheet pack")


class EngagementDocumentationDeleteRestrictionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="doc_del_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Del Doc Corp",
            client_short_name="DDC",
            client_code="DDC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY91",
            start_date=date(2090, 4, 1),
            end_date=date(2091, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Tax",
            service_code="TAX",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Plant A",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.doc_free = EngagementDocumentation.objects.create(
            standard_document="Unmapped Checklist",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_free.applicable_classifications.add(self.classification)
        self.doc_eng_mapped = EngagementDocumentation.objects.create(
            standard_document="Engagement Letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_eng_mapped.applicable_classifications.add(self.classification)
        EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.doc_eng_mapped,
            documentation_date=date(2090, 5, 1),
            created_by=self.user,
        )
        self.doc_div_mapped = EngagementDocumentation.objects.create(
            standard_document="Branch Memo",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_div_mapped.applicable_classifications.add(self.classification)
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.doc_div_mapped,
            created_by=self.user,
        )

    def test_delete_removes_unmapped_documentation(self):
        self.client.force_login(self.user)
        url = reverse("engagement_documentations")
        pk = self.doc_free.pk
        response = self.client.post(
            url,
            {"action": "delete", "pk": str(pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EngagementDocumentation.objects.filter(pk=pk).exists())

    def test_delete_blocked_when_mapped_to_engagement(self):
        self.client.force_login(self.user)
        url = reverse("engagement_documentations")
        pk = self.doc_eng_mapped.pk
        response = self.client.post(
            url,
            {"action": "delete", "pk": str(pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EngagementDocumentation.objects.filter(pk=pk).exists())
        self.assertContains(
            response,
            "mapped to an engagement or engagement division",
        )

    def test_delete_blocked_when_mapped_to_division_only(self):
        self.client.force_login(self.user)
        url = reverse("engagement_documentations")
        pk = self.doc_div_mapped.pk
        response = self.client.post(
            url,
            {"action": "delete", "pk": str(pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EngagementDocumentation.objects.filter(pk=pk).exists())
        self.assertContains(
            response,
            "mapped to an engagement or engagement division",
        )


class EngagementDocumentationMapFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eng_map_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Map Corp",
            client_short_name="Map",
            client_code="MAP1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY29",
            start_date=date(2028, 4, 1),
            end_date=date(2029, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Internal Audit",
            service_code="IADT",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        self.map_tm = TeamMember.objects.create(
            first_name="Map",
            last_name="User",
            called_as="Mapper",
            code="MP01",
            user=self.user,
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.map_tm,
            planned_start=self.fy.start_date,
            planned_finish=self.fy.end_date,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Engagement Letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.documentation_2 = EngagementDocumentation.objects.create(
            standard_document="Audit Plan",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation_2.applicable_classifications.add(self.classification)

    def test_queryset_excludes_documentation_for_other_classifications(self):
        llp, _ = ClientClassification.objects.get_or_create(
            classification_name="LLP",
            defaults={"created_by": self.user},
        )
        doc_llp = EngagementDocumentation.objects.create(
            standard_document="LLP-only letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        doc_llp.applicable_classifications.add(llp)
        form = EngagementDocumentationMapForm(engagement=self.engagement)
        ids = set(form.fields["documentation"].queryset.values_list("pk", flat=True))
        self.assertNotIn(doc_llp.pk, ids)
        self.assertIn(self.documentation.pk, ids)
        self.assertIn(self.documentation_2.pk, ids)

    def test_unique_documentation_mapping_per_engagement(self):
        EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2028, 5, 1),
            created_by=self.user,
        )
        form = EngagementDocumentationMapForm(
            data={
                "documentation": self.documentation.pk,
                "documentation_date": "2028-06-01",
            },
            engagement=self.engagement,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_queryset_hides_already_mapped_documentation_on_create(self):
        EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2028, 5, 1),
            created_by=self.user,
        )
        form = EngagementDocumentationMapForm(engagement=self.engagement)
        ids = set(form.fields["documentation"].queryset.values_list("pk", flat=True))
        self.assertNotIn(self.documentation.pk, ids)
        self.assertIn(self.documentation_2.pk, ids)

    def test_queryset_keeps_current_documentation_on_edit(self):
        mapping = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2028, 5, 1),
            created_by=self.user,
        )
        form = EngagementDocumentationMapForm(
            instance=mapping,
            engagement=self.engagement,
        )
        ids = set(form.fields["documentation"].queryset.values_list("pk", flat=True))
        self.assertIn(self.documentation.pk, ids)

    def test_create_view_accepts_multiple_documentation(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("engagement_documentation_map_create", args=[self.engagement.pk]),
            {
                "documentation": [str(self.documentation.pk), str(self.documentation_2.pk)],
                "documentation_date": "2028-07-15",
            },
        )
        self.assertEqual(response.status_code, 302)
        mapped_ids = set(
            EngagementDocumentationMap.objects.filter(
                engagement=self.engagement
            ).values_list("documentation_id", flat=True)
        )
        self.assertIn(self.documentation.pk, mapped_ids)
        self.assertIn(self.documentation_2.pk, mapped_ids)


class EngagementDivisionDocumentationMapFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="div_map_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Div Map Corp",
            client_short_name="DivMap",
            client_code="DMAP",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY30",
            start_date=date(2029, 4, 1),
            end_date=date(2030, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Assurance",
            service_code="ASUR",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2029, 4, 1),
            planned_finish=date(2029, 4, 30),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Division A",
            planned_start=date(2029, 4, 2),
            planned_finish=date(2029, 4, 28),
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Planning Memo",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.documentation_2 = EngagementDocumentation.objects.create(
            standard_document="Completion Memo",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation_2.applicable_classifications.add(self.classification)
        assign_user_to_engagement(self.user, self.engagement)

    def test_queryset_excludes_documentation_for_other_classifications(self):
        llp, _ = ClientClassification.objects.get_or_create(
            classification_name="Partnership Firm",
            defaults={"created_by": self.user},
        )
        doc_pf = EngagementDocumentation.objects.create(
            standard_document="Partnership-only memo",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        doc_pf.applicable_classifications.add(llp)
        form = EngagementDivisionDocumentationMapForm(division=self.division)
        ids = set(form.fields["documentation"].queryset.values_list("pk", flat=True))
        self.assertNotIn(doc_pf.pk, ids)
        self.assertIn(self.documentation.pk, ids)

    def test_unique_documentation_mapping_per_division(self):
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        form = EngagementDivisionDocumentationMapForm(
            data={
                "documentation": self.documentation.pk,
            },
            division=self.division,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_queryset_hides_already_mapped_documentation_on_create(self):
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        form = EngagementDivisionDocumentationMapForm(division=self.division)
        ids = set(form.fields["documentation"].queryset.values_list("pk", flat=True))
        self.assertNotIn(self.documentation.pk, ids)
        self.assertIn(self.documentation_2.pk, ids)

    def test_create_view_accepts_multiple_documentation(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_division_documentation_map_create",
                args=[self.division.pk],
            ),
            {
                "documentation": [str(self.documentation.pk), str(self.documentation_2.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        mapped_ids = set(
            EngagementDivisionDocumentationMap.objects.filter(
                division=self.division
            ).values_list("documentation_id", flat=True)
        )
        self.assertIn(self.documentation.pk, mapped_ids)
        self.assertIn(self.documentation_2.pk, mapped_ids)

    def test_delete_all_division_documentation_maps_removes_rows(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation_2,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse(
            "engagement_division_documentation_maps",
            kwargs={"division_pk": self.division.pk},
        )
        response = self.client.post(
            url,
            {"action": "delete_all_documentation_maps"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            EngagementDivisionDocumentationMap.objects.filter(
                division=self.division
            ).count(),
            0,
        )
        self.assertContains(response, "division documentation mapping(s)")

    def test_copy_documentation_from_another_division_adds_missing_mappings(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        source_division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Template Division",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=source_division,
            documentation=self.documentation,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=source_division,
            documentation=self.documentation_2,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_division_documentation_maps",
                kwargs={"division_pk": self.division.pk},
            ),
            {
                "action": "copy_from_division",
                "source_division_id": str(source_division.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        mapped_ids = set(
            EngagementDivisionDocumentationMap.objects.filter(
                division=self.division
            ).values_list("documentation_id", flat=True)
        )
        self.assertEqual(mapped_ids, {self.documentation.pk, self.documentation_2.pk})

    def test_copy_documentation_from_another_division_skips_existing_mappings(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        source_division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Template Division",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=source_division,
            documentation=self.documentation,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=source_division,
            documentation=self.documentation_2,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_division_documentation_maps",
                kwargs={"division_pk": self.division.pk},
            ),
            {
                "action": "copy_from_division",
                "source_division_id": str(source_division.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        mapped_ids = set(
            EngagementDivisionDocumentationMap.objects.filter(
                division=self.division
            ).values_list("documentation_id", flat=True)
        )
        self.assertEqual(mapped_ids, {self.documentation.pk, self.documentation_2.pk})

    def test_copy_documentation_rejects_source_from_other_fiscal_year(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        other_fy = FiscalYear.objects.create(
            fy_no="FY31",
            start_date=date(2030, 4, 1),
            end_date=date(2031, 3, 31),
            created_by=self.user,
        )
        other_engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=other_fy,
            service=self.service,
            created_by=self.user,
        )
        disallowed_source = EngagementDivision.objects.create(
            engagement=other_engagement,
            division_name="Other FY Division",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        EngagementDivisionDocumentationMap.objects.create(
            division=disallowed_source,
            documentation=self.documentation,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_division_documentation_maps",
                kwargs={"division_pk": self.division.pk},
            ),
            {
                "action": "copy_from_division",
                "source_division_id": str(disallowed_source.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            EngagementDivisionDocumentationMap.objects.filter(
                division=self.division
            ).count(),
            0,
        )


class EngagementDocumentationClassificationCascadeTests(TestCase):
    """Removing a client classification from setup doc drops orphan maps (no uploads)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cascade_doc_user",
            password="pass12345",
            is_superuser=True,
        )
        self.class_llp, _ = ClientClassification.objects.get_or_create(
            classification_name="LLP",
            defaults={"created_by": self.user},
        )
        self.class_others, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.corp = Client.objects.create(
            client_name="Cascade LLP Co",
            client_short_name="CLLP",
            client_code="CLP1",
            classification=self.class_llp,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY92",
            start_date=date(2091, 4, 1),
            end_date=date(2092, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUD",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.corp,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Unit 1",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Cascade test doc",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(
            self.class_llp, self.class_others
        )
        self.eng_map = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2091, 6, 1),
            created_by=self.user,
        )
        self.div_map = EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        self.edit_url = reverse(
            "engagement_documentation_edit",
            kwargs={"pk": self.documentation.pk},
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_removing_client_classification_deletes_maps_without_attachments(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.edit_url,
            {
                "standard_document": self.documentation.standard_document,
                "document_stage": self.documentation.document_stage,
                "applicable_classifications": [str(self.class_others.pk)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            EngagementDocumentationMap.objects.filter(pk=self.eng_map.pk).exists()
        )
        self.assertFalse(
            EngagementDivisionDocumentationMap.objects.filter(pk=self.div_map.pk).exists()
        )

    def test_maps_with_attachments_are_not_deleted(self):
        from django.core.files.base import ContentFile

        with override_settings(MEDIA_ROOT=self.media_dir):
            att = EngagementDocumentationMapAttachment(
                documentation_map=self.eng_map,
                original_filename="keep.txt",
                document_date=date(2091, 7, 1),
                created_by=self.user,
            )
            att.file.save("keep.txt", ContentFile(b"keep"), save=True)

        self.client.force_login(self.user)
        self.client.post(
            self.edit_url,
            {
                "standard_document": self.documentation.standard_document,
                "document_stage": self.documentation.document_stage,
                "applicable_classifications": [str(self.class_others.pk)],
            },
            follow=True,
        )
        self.assertTrue(
            EngagementDocumentationMap.objects.filter(pk=self.eng_map.pk).exists()
        )
        self.assertFalse(
            EngagementDivisionDocumentationMap.objects.filter(pk=self.div_map.pk).exists()
        )
        self.assertEqual(
            EngagementDocumentationMapAttachment.objects.filter(
                documentation_map=self.eng_map
            ).count(),
            1,
        )


class EngagementDocumentationPrefillTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="prefill_user",
            password="pass12345",
        )
        self.class_llp, _ = ClientClassification.objects.get_or_create(
            classification_name="LLP",
            defaults={"created_by": self.user},
        )
        self.class_others, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.corp = Client.objects.create(
            client_name="LLP Client Inc",
            client_short_name="LLPCl",
            client_code="LLP1",
            classification=self.class_llp,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY31",
            start_date=date(2030, 4, 1),
            end_date=date(2031, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="STAT",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.corp,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        self.prefill_member = TeamMember.objects.create(
            first_name="Pref",
            last_name="Fill",
            called_as="Prefill",
            code="PF01",
            user=self.user,
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.prefill_member,
            planned_start=self.fy.start_date,
            planned_finish=self.fy.end_date,
            created_by=self.user,
        )

        self.doc_llp_only = EngagementDocumentation.objects.create(
            standard_document="LLP-only letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_llp_only.applicable_classifications.add(self.class_llp)

        self.doc_others_only = EngagementDocumentation.objects.create(
            standard_document="Others-only memo",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_others_only.applicable_classifications.add(self.class_others)

        self.doc_both = EngagementDocumentation.objects.create(
            standard_document="Universal checklist",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_both.applicable_classifications.add(self.class_llp, self.class_others)

    def test_prefill_adds_only_matching_documentation(self):
        self.client.force_login(self.user)
        url = reverse(
            "engagement_documentation_maps",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        response = self.client.post(
            url,
            {"action": "prefill_from_client_classification"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        maps = EngagementDocumentationMap.objects.filter(engagement=self.engagement)
        self.assertEqual(maps.count(), 2)
        self.assertTrue(all(m.documentation_date for m in maps))
        mapped_ids = set(maps.values_list("documentation_id", flat=True))
        self.assertEqual(mapped_ids, {self.doc_llp_only.pk, self.doc_both.pk})

    def test_prefill_is_idempotent(self):
        self.client.force_login(self.user)
        url = reverse(
            "engagement_documentation_maps",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        self.client.post(url, {"action": "prefill_from_client_classification"})
        self.client.post(url, {"action": "prefill_from_client_classification"})
        maps = EngagementDocumentationMap.objects.filter(engagement=self.engagement)
        self.assertEqual(maps.count(), 2)

    def test_delete_all_documentation_maps_removes_rows(self):
        EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.doc_llp_only,
            documentation_date=date(2030, 5, 1),
            created_by=self.user,
        )
        EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.doc_both,
            documentation_date=date(2030, 5, 2),
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse(
            "engagement_documentation_maps",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        self.assertEqual(
            EngagementDocumentationMap.objects.filter(
                engagement=self.engagement
            ).count(),
            2,
        )
        response = self.client.post(
            url, {"action": "delete_all_documentation_maps"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            EngagementDocumentationMap.objects.filter(
                engagement=self.engagement
            ).count(),
            0,
        )
        self.assertContains(
            response, "documentation mapping(s) for this engagement"
        )


class EngagementDocumentationWordTemplateFillTests(TestCase):
    def test_fill_docx_replaces_contiguous_placeholder(self):
        from engagements.documentations.word_template_fill import fill_docx_template

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0"?><root><t>{{CLIENT_NAME}}</t></root>',
            )
            zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        buf.seek(0)
        filled = fill_docx_template(buf, {"{{CLIENT_NAME}}": "Ramco Ltd"})
        with zipfile.ZipFile(io.BytesIO(filled), "r") as z2:
            xml = z2.read("word/document.xml").decode()
        self.assertIn("Ramco Ltd", xml)
        self.assertNotIn("{{CLIENT_NAME}}", xml)

    def test_merge_context_includes_client_and_fy(self):
        from engagements.documentations.word_template_fill import (
            merge_context_for_engagement,
        )

        user = get_user_model().objects.create_user(
            username="merge_ctx_u",
            password="pass12345",
        )
        cl, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        c = Client.objects.create(
            client_name="Merge Co",
            client_short_name="Mrg",
            client_code="MRG1",
            classification=cl,
            address_1="Line A",
            city_state_pincode="Chennai",
            contact_person="Managing Director",
            is_active=True,
            created_by=user,
        )
        fy = FiscalYear.objects.create(
            fy_no="FY99",
            start_date=date(2098, 4, 1),
            end_date=date(2099, 3, 31),
            created_by=user,
        )
        svc = Service.objects.create(
            service_desc="Audit",
            service_code="AUD9",
            created_by=user,
        )
        eng = Engagement.objects.create(
            client=c,
            fiscal_year=fy,
            service=svc,
            created_by=user,
        )
        ctx = merge_context_for_engagement(eng)
        self.assertEqual(ctx["{{CLIENT_NAME}}"], "Merge Co")
        self.assertEqual(ctx["{{FY_YEAR}}"], "FY99")
        self.assertEqual(ctx["{{FY_END_YEAR}}"], "2099")
        self.assertEqual(ctx["{{FY_END_DATE_PHRASE}}"], "31 March 2099")
        self.assertEqual(ctx["{{FY_END_DAY_MONTH}}"], "31 March")
        self.assertEqual(ctx["{{YEAR_ENDED_PHRASE}}"], "year ended 31 March 2099")
        self.assertEqual(ctx["{{CLIENT_PLACE}}"], "Chennai")
        self.assertEqual(ctx["{{SIGNATORY_NAME}}"], "Managing Director")
        self.assertEqual(ctx["{{MR_DATE}}"], ctx["{{LETTER_DATE}}"])
        self.assertEqual(ctx["{{CLIENT_ADDRESS_LINE_1}}"], "Line A")
        self.assertIn("{{SERVICE_DESC}}", ctx)
        self.assertEqual(ctx["{{SERVICE_DESC}}"], "Audit")

    @override_settings(
        INVOICE_LETTERHEAD={
            "firm_name": "ALPHA & BETA",
            "firm_subtitle": "Chartered Accountants",
            "address_line_1": "12 Street, Cityville, Madurai 625001",
            "firm_office_city": "Trichy",
        }
    )
    def test_merge_context_auditor_to_lines_from_letterhead(self):
        from engagements.documentations.word_template_fill import (
            merge_context_for_engagement,
        )

        user = get_user_model().objects.create_user(
            username="aud_to_u",
            password="pass12345",
        )
        cl, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        c = Client.objects.create(
            client_name="Small Co",
            client_short_name="Sml",
            client_code="SML1",
            classification=cl,
            is_active=True,
            created_by=user,
        )
        fy = FiscalYear.objects.create(
            fy_no="FY01",
            start_date=date(2020, 4, 1),
            end_date=date(2021, 3, 31),
            created_by=user,
        )
        svc = Service.objects.create(
            service_desc="Audit",
            service_code="AUD1",
            created_by=user,
        )
        eng = Engagement.objects.create(
            client=c,
            fiscal_year=fy,
            service=svc,
            created_by=user,
        )
        ctx = merge_context_for_engagement(eng)
        self.assertEqual(ctx["{{AUDITOR_TO_LINE_1}}"], "Alpha & Beta")
        self.assertEqual(ctx["{{AUDITOR_TO_LINE_2}}"], "Chartered Accountants")
        self.assertEqual(ctx["{{AUDITOR_TO_LINE_3}}"], "Trichy")

    def test_merge_context_letter_date_uses_mapping_list_date(self):
        from engagements.documentations.word_template_fill import (
            merge_context_for_engagement,
        )

        user = get_user_model().objects.create_user(
            username="letter_date_u",
            password="pass12345",
        )
        cl, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        c = Client.objects.create(
            client_name="Letter Co",
            client_short_name="Ltr",
            client_code="LTR1",
            classification=cl,
            is_active=True,
            created_by=user,
        )
        fy = FiscalYear.objects.create(
            fy_no="FY26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            created_by=user,
        )
        svc = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="STAT",
            created_by=user,
        )
        eng = Engagement.objects.create(
            client=c,
            fiscal_year=fy,
            service=svc,
            created_by=user,
        )
        doc = EngagementDocumentation.objects.create(
            standard_document="Terms letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=user,
        )
        doc.applicable_classifications.add(cl)
        m = EngagementDocumentationMap.objects.create(
            engagement=eng,
            documentation=doc,
            documentation_date=date(2025, 7, 1),
            created_by=user,
        )
        ctx = merge_context_for_engagement(eng, documentation_map=m)
        self.assertEqual(ctx["{{LETTER_DATE}}"], "1.7.2025")

    def test_filled_docx_filename_matches_listing_pattern(self):
        from engagements.documentations.word_template_fill import (
            filled_engagement_documentation_docx_filename,
        )

        n = filled_engagement_documentation_docx_filename(
            documentation_date=date(2025, 7, 1),
            fy_no="FY26",
            client_code="RSLI",
            service_code="STAU",
            standard_document="Engagement terms",
        )
        self.assertEqual(n, "2025 07 01 FY26 RSLI STAU Engagement terms.docx")

    def test_filled_docx_filename_strips_invalid_chars(self):
        from engagements.documentations.word_template_fill import (
            filled_engagement_documentation_docx_filename,
        )

        n = filled_engagement_documentation_docx_filename(
            documentation_date=date(2025, 7, 1),
            fy_no="FY26",
            client_code="AB",
            service_code="CD",
            standard_document='Report <draft>: "v1"',
        )
        self.assertTrue(n.startswith("2025 07 01 FY26 AB CD "))
        self.assertTrue(n.endswith(".docx"))
        self.assertNotIn("<", n)
        self.assertNotIn('"', n)

    def test_filled_docx_filename_drops_redundant_statutory_audit_tail(self):
        from engagements.documentations.word_template_fill import (
            filled_engagement_documentation_docx_filename,
        )

        n = filled_engagement_documentation_docx_filename(
            documentation_date=date(2025, 7, 1),
            fy_no="FY26",
            client_code="RSLI",
            service_code="STAU",
            standard_document=(
                "Terms of engagement for statutory audit of corporate"
            ),
        )
        self.assertEqual(
            n,
            "2025 07 01 FY26 RSLI STAU Terms of engagement.docx",
        )

    def test_filled_docx_filename_uses_setup_download_label(self):
        from engagements.documentations.word_template_fill import (
            filled_engagement_documentation_docx_filename,
        )

        n = filled_engagement_documentation_docx_filename(
            documentation_date=date(2026, 5, 20),
            fy_no="FY26",
            client_code="RWFL",
            service_code="STAU",
            standard_document="Management Representation Company Policy",
            filled_download_label="MR 01",
        )
        self.assertEqual(n, "2026 05 20 FY26 RWFL STAU MR 01.docx")


class EngagementDocumentationMr02MatrixTests(TestCase):
    def test_parse_representation_matrix_post(self):
        from django.http import QueryDict

        from engagements.documentations.representation_matrix import (
            parse_representation_matrix_post,
        )

        q = QueryDict(mutable=True)
        q["mr02_status_p01"] = "complied"
        q["mr02_notes_p01"] = "  ok  "
        q["mr02_status_p02"] = "bogus"
        d = parse_representation_matrix_post(q)
        self.assertEqual(d["p01"]["status"], "complied")
        self.assertEqual(d["p01"]["notes"], "ok")
        self.assertNotIn("p02", d)

    def test_map_edit_saves_mr02_matrix(self):
        user = get_user_model().objects.create_user(
            username="mr02_u",
            password="pass12345",
        )
        user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        cl, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        corp = Client.objects.create(
            client_name="MR02 Client Inc",
            client_short_name="M02",
            client_code="M02C",
            classification=cl,
            is_active=True,
            created_by=user,
        )
        fy = FiscalYear.objects.create(
            fy_no="FY26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            created_by=user,
        )
        svc = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="STAU",
            created_by=user,
        )
        engagement = Engagement.objects.create(
            client=corp,
            fiscal_year=fy,
            service=svc,
            created_by=user,
        )
        tm = TeamMember.objects.create(
            first_name="MR",
            last_name="Editor",
            called_as="MR Editor",
            code="MR02",
            user=user,
            created_by=user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=engagement,
            team_member=tm,
            planned_start=fy.start_date,
            planned_finish=fy.end_date,
            created_by=user,
        )
        doc = EngagementDocumentation.objects.create(
            standard_document="Management Representation MR 02 pack",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            filled_download_label="MR 02",
            created_by=user,
        )
        doc.applicable_classifications.add(cl)
        m = EngagementDocumentationMap.objects.create(
            engagement=engagement,
            documentation=doc,
            documentation_date=date(2026, 5, 20),
            created_by=user,
        )
        url = reverse(
            "engagement_documentation_map_edit",
            kwargs={"engagement_pk": engagement.pk, "pk": m.pk},
        )
        self.client.force_login(user)
        response = self.client.post(
            url,
            {
                "documentation": str(doc.pk),
                "documentation_date": "2026-05-20",
                "mr02_status_p01": "complied",
                "mr02_notes_p01": "See WP-1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(
            m.representation_point_matrix.get("p01", {}).get("status"),
            "complied",
        )
        self.assertEqual(
            m.representation_point_matrix.get("p01", {}).get("notes"),
            "See WP-1",
        )


class EngagementDocumentationAttachmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="att_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Att Corp",
            client_short_name="Att",
            client_code="ATT1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY28",
            start_date=date(2027, 4, 1),
            end_date=date(2028, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Tax Audit",
            service_code="TAX",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Letter One",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.mapping = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2028, 1, 1),
            created_by=self.user,
        )
        self.maps_url = reverse(
            "engagement_documentation_maps",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        self.files_url = reverse(
            "engagement_documentation_map_files",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "map_pk": self.mapping.pk,
            },
        )
        self.media_dir = tempfile.mkdtemp()
        assign_user_to_engagement(self.user, self.engagement)

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_files_page_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(self.files_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documentation files")

    def test_upload_multiple_files(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
            f2 = SimpleUploadedFile("scan.pdf", b"%PDF-1.4", content_type="application/pdf")
            response = self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "files": [f1, f2],
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                EngagementDocumentationMapAttachment.objects.filter(
                    documentation_map=self.mapping
                ).count(),
                2,
            )
            names = set(
                self.mapping.attachments.values_list("original_filename", flat=True)
            )
            self.assertEqual(names, {"notes.txt", "scan.pdf"})
            for att in self.mapping.attachments.all():
                self.assertEqual(att.document_date, self.mapping.documentation_date)

    def test_upload_uses_posted_document_date(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("dated.txt", b"x", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "document_date": "2029-11-20",
                    "files": [f1],
                },
            )
            att = EngagementDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            self.assertEqual(att.document_date, date(2029, 11, 20))

    def test_upload_saves_description(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("desc.txt", b"x", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "description": "  Acceptance Letter with seal  ",
                    "files": [f1],
                },
            )
            att = EngagementDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            self.assertEqual(att.description, "Acceptance Letter with seal")

    def test_download_requires_login(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("keep.txt", b"payload", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "files": [f1],
                },
            )
            att = EngagementDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            url = reverse(
                "engagement_documentation_attachment_download",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "map_pk": self.mapping.pk,
                    "pk": att.pk,
                },
            )
            self.client.logout()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)

    def test_download_streams_file(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("keep.txt", b"payload", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "files": [f1],
                },
            )
            att = EngagementDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            url = reverse(
                "engagement_documentation_attachment_download",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "map_pk": self.mapping.pk,
                    "pk": att.pk,
                },
            )
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            body = b"".join(response.streaming_content)
            self.assertEqual(body, b"payload")

    def test_delete_attachment(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("gone.txt", b"x", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "files": [f1],
                },
            )
            att = EngagementDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            response = self.client.post(
                self.files_url,
                {"action": "delete_attachment", "pk": str(att.pk)},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.mapping.attachments.count(), 0)
            self.assertEqual(
                EngagementDocumentationMapAttachment.objects.filter(pk=att.pk).count(),
                0,
            )


class EngagementDocumentationMissingUploadsReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="miss_up_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Miss Up Corp",
            client_short_name="MUp",
            client_code="MUP1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY93",
            start_date=date(2092, 4, 1),
            end_date=date(2093, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Review",
            service_code="REV",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Region A",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.doc_a = EngagementDocumentation.objects.create(
            standard_document="Alpha Memo",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_a.applicable_classifications.add(self.classification)
        self.doc_b = EngagementDocumentation.objects.create(
            standard_document="Beta Pack",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            created_by=self.user,
        )
        self.doc_b.applicable_classifications.add(self.classification)
        self.eng_map_empty = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.doc_a,
            documentation_date=date(2092, 6, 1),
            created_by=self.user,
        )
        self.div_map_empty = EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.doc_b,
            created_by=self.user,
        )
        self.eng_map_with_file = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.doc_b,
            documentation_date=date(2092, 6, 2),
            created_by=self.user,
        )
        self.report_url = reverse(
            "engagement_documentation_missing_uploads_report",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_report_lists_only_maps_without_attachments(self):
        from django.core.files.base import ContentFile

        with override_settings(MEDIA_ROOT=self.media_dir):
            att = EngagementDocumentationMapAttachment(
                documentation_map=self.eng_map_with_file,
                original_filename="x.txt",
                document_date=date(2092, 7, 1),
                created_by=self.user,
            )
            att.file.save("x.txt", ContentFile(b"x"), save=True)

        self.client.force_login(self.user)
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Memo")
        self.assertContains(response, "Division: Region A")
        self.assertContains(response, "Beta Pack", count=1)
        busy_files_url = reverse(
            "engagement_documentation_map_files",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "map_pk": self.eng_map_with_file.pk,
            },
        )
        self.assertNotContains(response, busy_files_url)
        self.assertContains(
            response,
            reverse(
                "engagement_documentation_map_files",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "map_pk": self.eng_map_empty.pk,
                },
            ),
        )


class EngagementDivisionDocumentationAttachmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="div_att_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Div Att Corp",
            client_short_name="DivAtt",
            client_code="DATT",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY40",
            start_date=date(2039, 4, 1),
            end_date=date(2040, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Division Audit",
            service_code="DIVA",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Main Branch",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Division Checklist",
            document_stage=EngagementDocumentation.POST_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.mapping = EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        self.maps_url = reverse(
            "engagement_division_documentation_maps",
            kwargs={"division_pk": self.division.pk},
        )
        self.files_url = reverse(
            "engagement_division_documentation_map_files",
            kwargs={
                "division_pk": self.division.pk,
                "map_pk": self.mapping.pk,
            },
        )
        self.media_dir = tempfile.mkdtemp()
        assign_user_to_engagement(self.user, self.engagement)

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_files_page_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(self.files_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Division documentation files")

    def test_upload_multiple_files(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("div-1.txt", b"hello", content_type="text/plain")
            f2 = SimpleUploadedFile(
                "div-2.pdf", b"%PDF-1.4", content_type="application/pdf"
            )
            response = self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "document_date": "2040-01-05",
                    "files": [f1, f2],
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                EngagementDivisionDocumentationMapAttachment.objects.filter(
                    documentation_map=self.mapping
                ).count(),
                2,
            )
            names = set(
                self.mapping.attachments.values_list("original_filename", flat=True)
            )
            self.assertEqual(names, {"div-1.txt", "div-2.pdf"})

    def test_delete_attachment(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("gone-div.txt", b"x", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "document_date": "2040-01-06",
                    "files": [f1],
                },
            )
            att = EngagementDivisionDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            response = self.client.post(
                self.files_url,
                {"action": "delete_attachment", "pk": str(att.pk)},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.mapping.attachments.count(), 0)

    def test_upload_saves_description(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("div-desc.txt", b"x", content_type="text/plain")
            self.client.post(
                self.files_url,
                data={
                    "action": "upload_attachment",
                    "document_date": "2040-01-06",
                    "description": "  Branch checklist support  ",
                    "files": [f1],
                },
            )
            att = EngagementDivisionDocumentationMapAttachment.objects.get(
                documentation_map=self.mapping
            )
            self.assertEqual(att.description, "Branch checklist support")

class EngagementWorkAreaDocumentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="wa_doc_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="WA Doc Corp",
            client_short_name="WADoc",
            client_code="WADC",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY41",
            start_date=date(2040, 4, 1),
            end_date=date(2041, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Documentation",
            service_code="DOCS",
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Appointment Letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Tax Filing",
            sort_order=1,
            created_by=self.user,
        )
        self.docs_url = reverse(
            "engagement_work_area_documents",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_direct_upload_action_is_retired(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("wa-notes.txt", b"n1", content_type="text/plain")
            response = self.client.post(
                self.docs_url,
                data={
                    "action": "upload_document",
                    "document_date": "2040-07-15",
                    "documentation_id": str(self.documentation.pk),
                    "files": [f1],
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertFalse(
                EngagementWorkAreaDocument.objects.filter(
                    work_area=self.work_area
                ).exists()
            )

    def test_note_attachment_with_reference_no(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            query = AuditQuery.objects.create(
                engagement_work_area=self.work_area,
                query_date=date(2040, 7, 15),
                subject="GST reconciliation",
                query_text="Provide GST reconciliation.",
                created_by=self.user,
            )
            queries_url = reverse(
                "engagement_work_area_queries",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "work_area_pk": self.work_area.pk,
                },
            )
            f1 = SimpleUploadedFile("recon.xlsx", b"x1", content_type="application/octet-stream")
            response = self.client.post(
                queries_url,
                data={
                    "action": "add_query_attachment",
                    "query_pk": str(query.pk),
                    "attachment_file": f1,
                    "document_reference_no": "  REF-2040/15  ",
                },
            )
            self.assertEqual(response.status_code, 302)
            att = AuditQueryAttachment.objects.get(query=query)
            self.assertEqual(att.document_reference_no, "REF-2040/15")
            docs_page = self.client.get(self.docs_url)
            self.assertContains(docs_page, "REF-2040/15")


class DivisionWorkAreaDocumentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dwa_doc_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="DWA Doc Corp",
            client_short_name="DWADoc",
            client_code="DWDC",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY44",
            start_date=date(2043, 4, 1),
            end_date=date(2044, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Division Support",
            service_code="DSUP",
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Division Appointment Letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="North Zone",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Division Tax Filing",
            sort_order=1,
            created_by=self.user,
        )
        self.docs_url = reverse(
            "engagement_division_work_area_documents",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_direct_upload_action_is_retired(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.force_login(self.user)
            f1 = SimpleUploadedFile("dwa-notes.txt", b"n1", content_type="text/plain")
            response = self.client.post(
                self.docs_url,
                data={
                    "action": "upload_document",
                    "document_date": "2043-07-15",
                    "documentation_id": str(self.documentation.pk),
                    "files": [f1],
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertFalse(
                DivisionWorkAreaDocument.objects.filter(
                    work_area=self.work_area
                ).exists()
            )


class DivisionWorkAreaStatusRemarkTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dwa_status_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="DWA Status Corp",
            client_short_name="DWAStatus",
            client_code="DWAS",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY46",
            start_date=date(2045, 4, 1),
            end_date=date(2046, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Status",
            service_code="STAT",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="South",
            created_by=self.user,
        )
        self.work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Schedule verification",
            sort_order=1,
            created_by=self.user,
        )
        self.url = reverse(
            "engagement_division_work_area_status_remarks",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        assign_user_to_engagement(self.user, self.engagement)

    def test_add_status_remark(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={
                "action": "add_remark",
                "remark_date": "2045-10-12",
                "remarks": "  Follow up with branch manager  ",
            },
        )
        self.assertEqual(response.status_code, 302)
        remark = DivisionWorkAreaStatusRemark.objects.get(work_area=self.work_area)
        self.assertEqual(remark.remark_date, date(2045, 10, 12))
        self.assertEqual(remark.remarks, "Follow up with branch manager")


class StatusRemarksReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="status_report_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Status Report Corp",
            client_short_name="SRC",
            client_code="SRC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY47",
            start_date=date(2046, 4, 1),
            end_date=date(2047, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Compliance",
            service_code="COMP",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="West",
            created_by=self.user,
        )
        self.eng_work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Ledger review",
            sort_order=1,
            created_by=self.user,
        )
        self.div_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Branch review",
            sort_order=1,
            created_by=self.user,
        )

    def test_status_remarks_report_shows_all_levels(self):
        AuditQuery.objects.create(
            engagement_work_area=self.eng_work_area,
            query_date=date(2046, 5, 3),
            entry_type=AuditQuery.ENTRY_TYPE_REMARK,
            subject="Eng WA note",
            query_text="Eng WA note",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            status=AuditQuery.STATUS_CLOSED,
            created_by=self.user,
        )
        AuditQuery.objects.create(
            division_work_area=self.div_work_area,
            query_date=date(2046, 5, 4),
            entry_type=AuditQuery.ENTRY_TYPE_REMARK,
            subject="Div WA note",
            query_text="Div WA note",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            status=AuditQuery.STATUS_CLOSED,
            created_by=self.user,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("status_remarks_report"))
        self.assertRedirects(
            response,
            f"{reverse('work_area_notes_report')}?type=remark",
            fetch_redirect_response=False,
        )
        response = self.client.get(reverse("work_area_notes_report"), {"type": "remark"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Eng WA note")
        self.assertContains(response, "Div WA note")


class AuditQueryFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="audit_query_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="AQ Corp",
            client_short_name="AQ",
            client_code="AQ1",
            classification=self.classification,
            mail_id="client@example.com",
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY48",
            start_date=date(2047, 4, 1),
            end_date=date(2048, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUD",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="PPE",
            sort_order=1,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="North Unit",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.division_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Branch PPE",
            sort_order=1,
            created_by=self.user,
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_convert_query_to_working_paper(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 1),
            subject="Has FAS tallied with TB?",
            query_text="Check reconciliation.",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse(
            "engagement_work_area_queries",
            kwargs={"engagement_pk": self.engagement.pk, "work_area_pk": self.work_area.pk},
        )
        response = self.client.post(
            url,
            data={"action": "convert_to_working_paper", "query_pk": str(query.pk)},
        )
        self.assertEqual(response.status_code, 302)
        query.refresh_from_db()
        self.assertTrue(query.converted_to_working_paper)
        self.assertTrue(query.working_paper_no.startswith("AWP-Q"))

    def test_draft_mail_logs_once_and_requires_repeat_override(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 1),
            subject="Client confirmation pending",
            query_text="Please share confirmation.",
            response_expected_from=AuditQuery.RESPONDER_CLIENT,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        draft_url = reverse("audit_query_open_draft", kwargs={"query_pk": query.pk})

        first = self.client.get(draft_url)
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, "mailto:")
        self.assertEqual(AuditQueryMailDraftLog.objects.filter(audit_query=query).count(), 1)

        second = self.client.get(draft_url)
        self.assertEqual(second.status_code, 302)
        self.assertIn(reverse("work_area_notes_report"), second["Location"])
        self.assertEqual(AuditQueryMailDraftLog.objects.filter(audit_query=query).count(), 1)

        repeat = self.client.get(f"{draft_url}?repeat=1")
        self.assertEqual(repeat.status_code, 200)
        self.assertContains(repeat, "mailto:")
        self.assertEqual(AuditQueryMailDraftLog.objects.filter(audit_query=query).count(), 2)

    def test_engagement_all_work_area_notes_lists_engagement_and_division_queries(self):
        AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 10),
            subject="Eng-level subject",
            query_text="Eng body",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        AuditQuery.objects.create(
            division_work_area=self.division_work_area,
            query_date=date(2047, 6, 11),
            subject="Div-level subject",
            query_text="Div body",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        url = reverse(
            "engagement_all_work_area_notes",
            kwargs={"engagement_pk": self.engagement.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Eng-level subject")
        self.assertContains(response, "Div-level subject")
        self.assertContains(response, "Engagement (no division)")
        self.assertContains(response, "Division: North Unit")
        self.assertContains(response, "PPE")
        self.assertContains(response, "Branch PPE")

    def test_can_upload_and_download_query_attachment_for_engagement_work_area(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 2),
            subject="Attach ledgers",
            query_text="Need backup documents.",
            response_expected_from=AuditQuery.RESPONDER_CLIENT,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            page_url = reverse(
                "engagement_work_area_queries",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "work_area_pk": self.work_area.pk,
                },
            )
            response = self.client.post(
                page_url,
                data={
                    "action": "add_query_attachment",
                    "query_pk": str(query.pk),
                    "attachment_file": SimpleUploadedFile(
                        "ledger.pdf", b"pdf-bytes", content_type="application/pdf"
                    ),
                },
            )
            self.assertEqual(response.status_code, 302)
            attachment = AuditQueryAttachment.objects.get(query=query)
            self.assertEqual(attachment.original_filename, "ledger.pdf")

            download_url = reverse(
                "engagement_query_attachment_download",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "work_area_pk": self.work_area.pk,
                    "query_pk": query.pk,
                    "pk": attachment.pk,
                },
            )
            download = self.client.get(download_url)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(
                download["Content-Disposition"],
                'attachment; filename="ledger.pdf"',
            )

    def test_can_upload_and_download_query_attachment_for_division_work_area(self):
        query = AuditQuery.objects.create(
            division_work_area=self.division_work_area,
            query_date=date(2047, 6, 3),
            subject="Attach branch proof",
            query_text="Need branch-level support.",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            page_url = reverse(
                "engagement_division_work_area_queries",
                kwargs={
                    "division_pk": self.division.pk,
                    "work_area_pk": self.division_work_area.pk,
                },
            )
            response = self.client.post(
                page_url,
                data={
                    "action": "add_query_attachment",
                    "query_pk": str(query.pk),
                    "attachment_file": SimpleUploadedFile(
                        "branch-note.txt", b"note", content_type="text/plain"
                    ),
                },
            )
            self.assertEqual(response.status_code, 302)
            attachment = AuditQueryAttachment.objects.get(query=query)
            self.assertEqual(attachment.original_filename, "branch-note.txt")

            download_url = reverse(
                "engagement_division_query_attachment_download",
                kwargs={
                    "division_pk": self.division.pk,
                    "work_area_pk": self.division_work_area.pk,
                    "query_pk": query.pk,
                    "pk": attachment.pk,
                },
            )
            download = self.client.get(download_url)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(
                download["Content-Disposition"],
                'attachment; filename="branch-note.txt"',
            )

    def test_add_query_batch_creates_rows_and_updates_work_area_amount(self):
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(engagement_work_area=self.work_area).count()
        response = self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "12.5",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-06-04", "2047-06-05"],
                "batch_row_type": [
                    AuditQuery.ENTRY_TYPE_QUERY,
                    AuditQuery.ENTRY_TYPE_REMARK,
                ],
                "batch_row_checklist": ["", ""],
                "batch_row_expected": [
                    AuditQuery.RESPONDER_CLIENT,
                    AuditQuery.RESPONDER_INTERNAL,
                ],
                "batch_row_text": ["First line", "Second line"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 2,
        )
        self.work_area.refresh_from_db()
        self.assertEqual(self.work_area.monetary_amount, Decimal("12.50"))
        self.assertEqual(self.work_area.monetary_amount_unit, AuditQuery.AMOUNT_UNIT_LAKHS)

    def test_save_query_batch_row_json_engagement(self):
        import json

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(engagement_work_area=self.work_area).count()
        response = self.client.post(
            page_url,
            data={
                "action": "save_query_batch_row",
                "batch_row_save_index": "0",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-08-01"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [""],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Single async line"],
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        self.assertTrue(json.loads(response.content)["ok"])
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 1,
        )
        self.assertTrue(
            AuditQuery.objects.filter(
                engagement_work_area=self.work_area, query_text="Single async line"
            ).exists()
        )

    def test_save_query_batch_row_json_checklist_only_without_query_text(self):
        import json

        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Statutory liabilities payable",
            sort_order=2,
            created_by=self.user,
        )
        item = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Ensure that the dues are liquidated in time",
            sort_order=1,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(engagement_work_area=self.work_area).count()
        response = self.client.post(
            page_url,
            data={
                "action": "save_query_batch_row",
                "batch_row_save_index": "0",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-08-10", "2047-08-11"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY, AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [str(item.pk), ""],
                "batch_row_checklist_label": [item.line_text, ""],
                "batch_row_expected": [
                    AuditQuery.RESPONDER_INTERNAL,
                    AuditQuery.RESPONDER_INTERNAL,
                ],
                "batch_row_text": ["", ""],
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)["ok"])
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 1,
        )
        saved = AuditQuery.objects.get(
            engagement_work_area=self.work_area,
            service_checklist_item_id=item.pk,
        )
        self.assertEqual(saved.query_text, item.line_text)

    def test_save_query_batch_row_json_uses_checklist_label_when_picker_id_stale(self):
        import json

        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Stale id WA",
            sort_order=3,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])
        stale_id = 999999001

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        label = "Ensure liability reflects recent deduction"
        response = self.client.post(
            page_url,
            data={
                "action": "save_query_batch_row",
                "batch_row_save_index": "0",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-08-12"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [str(stale_id)],
                "batch_row_checklist_label": [label],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": [""],
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)["ok"])
        self.assertTrue(
            AuditQuery.objects.filter(
                engagement_work_area=self.work_area, query_text=label
            ).exists()
        )

    def test_save_query_batch_row_json_division(self):
        import json

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.division_work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(division_work_area=self.division_work_area).count()
        response = self.client.post(
            page_url,
            data={
                "action": "save_query_batch_row",
                "batch_row_save_index": "0",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-08-02"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [""],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Division async line"],
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)["ok"])
        self.assertEqual(
            AuditQuery.objects.filter(division_work_area=self.division_work_area).count(),
            before + 1,
        )
        self.assertTrue(
            AuditQuery.objects.filter(
                division_work_area=self.division_work_area, query_text="Division async line"
            ).exists()
        )

    def test_add_query_batch_attaches_files_per_row(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            page_url = reverse(
                "engagement_work_area_queries",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "work_area_pk": self.work_area.pk,
                },
            )
            response = self.client.post(
                page_url,
                data={
                    "action": "add_query_batch",
                    "batch_wa_amount": "",
                    "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                    "batch_row_date": ["2047-06-04"],
                    "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                    "batch_row_checklist": [""],
                    "batch_row_expected": [AuditQuery.RESPONDER_CLIENT],
                    "batch_row_text": ["Please review attachments."],
                    "batch_row_files_0": [
                        SimpleUploadedFile("q1.txt", b"one", content_type="text/plain"),
                        SimpleUploadedFile("q2.txt", b"two", content_type="text/plain"),
                    ],
                },
            )
            self.assertEqual(response.status_code, 302)
            query = AuditQuery.objects.get(query_text="Please review attachments.")
            self.assertEqual(query.attachments.count(), 2)

    def test_add_query_batch_allows_note_without_checklist_when_template_linked(self):
        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Template WA",
            sort_order=0,
            created_by=self.user,
        )
        item = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Verify cash",
            sort_order=0,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(engagement_work_area=self.work_area).count()
        self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-06-06"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_REMARK],
                "batch_row_checklist": [""],
                "batch_row_checklist_label": [""],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Free-form remark without checklist"],
            },
        )
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 1,
        )
        free_note = AuditQuery.objects.get(query_text="Free-form remark without checklist")
        self.assertIsNone(free_note.service_checklist_item_id)

        self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-06-06"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [str(item.pk)],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["With checklist"],
            },
        )
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 2,
        )
        q = AuditQuery.objects.get(query_text="With checklist")
        self.assertEqual(q.service_checklist_item_id, item.pk)

    def test_add_all_checklist_lines_to_notes_log(self):
        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Full template WA",
            sort_order=0,
            created_by=self.user,
        )
        item_a = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Line A",
            sort_order=0,
            created_by=self.user,
        )
        item_b = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Line B",
            sort_order=1,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])
        AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 1),
            entry_type=AuditQuery.ENTRY_TYPE_QUERY,
            subject="Existing",
            query_text="Line A",
            service_checklist_item=item_a,
            created_by=self.user,
        )

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        response = self.client.post(
            page_url,
            {"action": "add_all_checklist_lines"},
        )
        self.assertEqual(response.status_code, 302)
        linked_ids = set(
            AuditQuery.objects.filter(engagement_work_area=self.work_area)
            .exclude(service_checklist_item__isnull=True)
            .values_list("service_checklist_item_id", flat=True)
        )
        self.assertEqual(linked_ids, {item_a.pk, item_b.pk})

        response_repeat = self.client.post(
            page_url,
            {"action": "add_all_checklist_lines"},
            follow=True,
        )
        self.assertEqual(response_repeat.status_code, 200)
        self.assertContains(response_repeat, "already in the notes log")

    def test_add_query_batch_checklist_only_without_query_text(self):
        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Template WA checklist only",
            sort_order=2,
            created_by=self.user,
        )
        item = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Is the total of FA Register matching with FA Schedule",
            sort_order=0,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(engagement_work_area=self.work_area).count()
        response = self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-06-08", "2047-06-09"],
                "batch_row_type": [
                    AuditQuery.ENTRY_TYPE_QUERY,
                    AuditQuery.ENTRY_TYPE_QUERY,
                ],
                "batch_row_checklist": [str(item.pk), ""],
                "batch_row_checklist_label": [
                    "Is the total of FA Register matching with FA Schedule",
                    "Calculate depreciation by downloading the data an excel sheet",
                ],
                "batch_row_expected": [
                    AuditQuery.RESPONDER_INTERNAL,
                    AuditQuery.RESPONDER_INTERNAL,
                ],
                "batch_row_text": ["", ""],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=self.work_area).count(),
            before + 2,
        )
        picked = AuditQuery.objects.get(
            service_checklist_item_id=item.pk,
            engagement_work_area=self.work_area,
        )
        self.assertEqual(
            picked.query_text,
            "Is the total of FA Register matching with FA Schedule",
        )
        typed = AuditQuery.objects.get(
            query_text="Calculate depreciation by downloading the data an excel sheet",
            engagement_work_area=self.work_area,
        )
        self.assertIsNone(typed.service_checklist_item_id)
        self.assertIn("Calculate depreciation", typed.subject)

    def test_add_query_batch_free_text_checklist_label_without_picker(self):
        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Template WA 2",
            sort_order=1,
            created_by=self.user,
        )
        self.work_area.service_checklist_work_area = tpl
        self.work_area.save(update_fields=["service_checklist_work_area"])

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-06-07"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [""],
                "batch_row_checklist_label": ["Custom line not in template"],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Ad hoc query text"],
            },
        )
        q = AuditQuery.objects.get(query_text="Ad hoc query text")
        self.assertIsNone(q.service_checklist_item_id)
        self.assertIn("Custom line not in template", q.subject)

    def test_division_add_query_batch_creates_rows_and_updates_work_area_amount(self):
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.division_work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(
            division_work_area=self.division_work_area
        ).count()
        response = self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "3.25",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_CRORES,
                "batch_row_date": ["2047-07-01"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [""],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Division batch line"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AuditQuery.objects.filter(
                division_work_area=self.division_work_area
            ).count(),
            before + 1,
        )
        self.division_work_area.refresh_from_db()
        self.assertEqual(self.division_work_area.monetary_amount, Decimal("3.25"))
        self.assertEqual(
            self.division_work_area.monetary_amount_unit,
            AuditQuery.AMOUNT_UNIT_CRORES,
        )

    def test_division_add_query_batch_attaches_files_per_row(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            page_url = reverse(
                "engagement_division_work_area_queries",
                kwargs={
                    "division_pk": self.division.pk,
                    "work_area_pk": self.division_work_area.pk,
                },
            )
            response = self.client.post(
                page_url,
                data={
                    "action": "add_query_batch",
                    "batch_wa_amount": "",
                    "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                    "batch_row_date": ["2047-07-02"],
                    "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                    "batch_row_checklist": [""],
                    "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                    "batch_row_text": ["Division row with files"],
                    "batch_row_files_0": [
                        SimpleUploadedFile(
                            "d1.txt", b"a", content_type="text/plain"
                        ),
                    ],
                },
            )
            self.assertEqual(response.status_code, 302)
            query = AuditQuery.objects.get(query_text="Division row with files")
            self.assertEqual(query.attachments.count(), 1)

    def test_division_add_query_batch_allows_note_without_checklist_when_template_linked(
        self,
    ):
        tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Div template WA",
            sort_order=1,
            created_by=self.user,
        )
        item = ServiceEngagementChecklistItem.objects.create(
            work_area=tpl,
            line_text="Count petty cash",
            sort_order=0,
            created_by=self.user,
        )
        self.division_work_area.service_checklist_work_area = tpl
        self.division_work_area.save(update_fields=["service_checklist_work_area"])

        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.division_work_area.pk,
            },
        )
        before = AuditQuery.objects.filter(
            division_work_area=self.division_work_area
        ).count()
        self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-07-03"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_REMARK],
                "batch_row_checklist": [""],
                "batch_row_checklist_label": [""],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Div remark without checklist"],
            },
        )
        self.assertEqual(
            AuditQuery.objects.filter(
                division_work_area=self.division_work_area
            ).count(),
            before + 1,
        )

        self.client.post(
            page_url,
            data={
                "action": "add_query_batch",
                "batch_wa_amount": "",
                "batch_wa_amount_unit": AuditQuery.AMOUNT_UNIT_LAKHS,
                "batch_row_date": ["2047-07-03"],
                "batch_row_type": [AuditQuery.ENTRY_TYPE_QUERY],
                "batch_row_checklist": [str(item.pk)],
                "batch_row_expected": [AuditQuery.RESPONDER_INTERNAL],
                "batch_row_text": ["Div with checklist"],
            },
        )
        self.assertEqual(
            AuditQuery.objects.filter(
                division_work_area=self.division_work_area
            ).count(),
            before + 2,
        )
        q = AuditQuery.objects.get(query_text="Div with checklist")
        self.assertEqual(q.service_checklist_item_id, item.pk)

    def test_can_edit_existing_engagement_query_note(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 5),
            subject="Old subject",
            query_text="Old details",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            amount=10,
            amount_unit=AuditQuery.AMOUNT_UNIT_LAKHS,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        response = self.client.post(
            page_url,
            data={
                "action": "edit_query",
                "query_pk": str(query.pk),
                "subject": "Updated subject",
                "amount": "-12.50",
                "amount_unit": AuditQuery.AMOUNT_UNIT_RS,
                "response_expected_from": AuditQuery.RESPONDER_CLIENT,
                "query_text": "Updated details",
            },
        )
        self.assertEqual(response.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.subject, "Updated subject")
        self.assertEqual(str(query.amount), "-12.50")
        self.assertEqual(query.amount_unit, AuditQuery.AMOUNT_UNIT_RS)
        self.assertEqual(query.response_expected_from, AuditQuery.RESPONDER_CLIENT)
        self.assertEqual(query.query_text, "Updated details")

    def test_can_edit_existing_division_query_note(self):
        query = AuditQuery.objects.create(
            division_work_area=self.division_work_area,
            query_date=date(2047, 6, 6),
            subject="Div old",
            query_text="Div old details",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            amount=25,
            amount_unit=AuditQuery.AMOUNT_UNIT_LAKHS,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.division_work_area.pk,
            },
        )
        response = self.client.post(
            page_url,
            data={
                "action": "edit_query",
                "query_pk": str(query.pk),
                "subject": "Div updated",
                "amount": "0",
                "amount_unit": AuditQuery.AMOUNT_UNIT_CRORES,
                "response_expected_from": AuditQuery.RESPONDER_CLIENT,
                "query_text": "Div updated details",
            },
        )
        self.assertEqual(response.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.subject, "Div updated")
        self.assertEqual(str(query.amount), "0.00")
        self.assertEqual(query.amount_unit, AuditQuery.AMOUNT_UNIT_CRORES)
        self.assertEqual(query.response_expected_from, AuditQuery.RESPONDER_CLIENT)
        self.assertEqual(query.query_text, "Div updated details")

    def test_can_delete_engagement_query_note(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 7),
            subject="Delete me",
            query_text="Temp row",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_work_area_queries",
            kwargs={
                "engagement_pk": self.engagement.pk,
                "work_area_pk": self.work_area.pk,
            },
        )
        response = self.client.post(
            page_url,
            data={
                "action": "delete_query",
                "query_pk": str(query.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AuditQuery.objects.filter(pk=query.pk).exists())

    def test_can_delete_division_query_note(self):
        query = AuditQuery.objects.create(
            division_work_area=self.division_work_area,
            query_date=date(2047, 6, 8),
            subject="Delete div",
            query_text="Temp row div",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        page_url = reverse(
            "engagement_division_work_area_queries",
            kwargs={
                "division_pk": self.division.pk,
                "work_area_pk": self.division_work_area.pk,
            },
        )
        response = self.client.post(
            page_url,
            data={
                "action": "delete_query",
                "query_pk": str(query.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AuditQuery.objects.filter(pk=query.pk).exists())

    def test_can_delete_query_attachment_from_engagement_query(self):
        query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2047, 6, 11),
            subject="With attachment",
            query_text="Has file",
            response_expected_from=AuditQuery.RESPONDER_INTERNAL,
            created_by=self.user,
        )
        with override_settings(MEDIA_ROOT=self.media_dir):
            attachment = AuditQueryAttachment.objects.create(
                query=query,
                file=SimpleUploadedFile("dup.txt", b"dup", content_type="text/plain"),
                original_filename="dup.txt",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            page_url = reverse(
                "engagement_work_area_queries",
                kwargs={
                    "engagement_pk": self.engagement.pk,
                    "work_area_pk": self.work_area.pk,
                },
            )
            response = self.client.post(
                page_url,
                data={
                    "action": "delete_query_attachment",
                    "query_pk": str(query.pk),
                    "attachment_pk": str(attachment.pk),
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertFalse(AuditQueryAttachment.objects.filter(pk=attachment.pk).exists())


class EngagementUploadedDocumentsReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="uploaded_report_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Report Corp",
            client_short_name="Rpt",
            client_code="RPT1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY45",
            start_date=date(2044, 4, 1),
            end_date=date(2045, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Reporting",
            service_code="RPTG",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Chennai",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.eng_work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Planning",
            sort_order=1,
            created_by=self.user,
        )
        self.div_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Branch planning",
            sort_order=1,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Engagement Letter",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.eng_map = EngagementDocumentationMap.objects.create(
            engagement=self.engagement,
            documentation=self.documentation,
            documentation_date=date(2044, 5, 1),
            created_by=self.user,
        )
        self.div_map = EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_report_lists_all_uploaded_document_sources(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            EngagementDocumentationMapAttachment.objects.create(
                documentation_map=self.eng_map,
                file=SimpleUploadedFile("eng-doc.pdf", b"a", content_type="application/pdf"),
                original_filename="eng-doc.pdf",
                document_date=date(2044, 5, 2),
                created_by=self.user,
            )
            EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_map,
                file=SimpleUploadedFile("div-doc.pdf", b"b", content_type="application/pdf"),
                original_filename="div-doc.pdf",
                document_date=date(2044, 5, 3),
                created_by=self.user,
            )
            EngagementWorkAreaDocument.objects.create(
                work_area=self.eng_work_area,
                document_date=date(2044, 5, 4),
                description="Planning file",
                file=SimpleUploadedFile("eng-wa.txt", b"c", content_type="text/plain"),
                original_filename="eng-wa.txt",
                created_by=self.user,
            )
            DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 5),
                description="Branch plan",
                file=SimpleUploadedFile("div-wa.txt", b"d", content_type="text/plain"),
                original_filename="div-wa.txt",
                created_by=self.user,
            )
            eng_query = AuditQuery.objects.create(
                engagement_work_area=self.eng_work_area,
                query_date=date(2044, 5, 6),
                subject="Eng WA query",
                query_text="Details",
                response_expected_from=AuditQuery.RESPONDER_INTERNAL,
                created_by=self.user,
            )
            AuditQueryAttachment.objects.create(
                query=eng_query,
                file=SimpleUploadedFile("eng-query.xlsx", b"x", content_type="application/vnd.ms-excel"),
                original_filename="eng-query.xlsx",
                created_by=self.user,
            )
            div_query = AuditQuery.objects.create(
                division_work_area=self.div_work_area,
                query_date=date(2044, 5, 7),
                subject="Div WA query",
                query_text="Details",
                response_expected_from=AuditQuery.RESPONDER_INTERNAL,
                created_by=self.user,
            )
            AuditQueryAttachment.objects.create(
                query=div_query,
                file=SimpleUploadedFile("div-query.xlsx", b"y", content_type="application/vnd.ms-excel"),
                original_filename="div-query.xlsx",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_uploaded_documents_report",
                    kwargs={"engagement_pk": self.engagement.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "eng-doc.pdf")
            self.assertContains(response, "div-doc.pdf")
            self.assertContains(response, "eng-wa.txt")
            self.assertContains(response, "div-wa.txt")
            self.assertContains(response, "eng-query.xlsx")
            self.assertContains(response, "div-query.xlsx")

    def test_division_uploaded_documents_report_lists_only_division_sources(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            EngagementDocumentationMapAttachment.objects.create(
                documentation_map=self.eng_map,
                file=SimpleUploadedFile("eng-doc.pdf", b"a", content_type="application/pdf"),
                original_filename="eng-doc.pdf",
                document_date=date(2044, 5, 2),
                created_by=self.user,
            )
            EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_map,
                file=SimpleUploadedFile("div-doc.pdf", b"b", content_type="application/pdf"),
                original_filename="div-doc.pdf",
                document_date=date(2044, 5, 3),
                created_by=self.user,
            )
            EngagementWorkAreaDocument.objects.create(
                work_area=self.eng_work_area,
                document_date=date(2044, 5, 4),
                description="Planning file",
                file=SimpleUploadedFile("eng-wa.txt", b"c", content_type="text/plain"),
                original_filename="eng-wa.txt",
                created_by=self.user,
            )
            DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 5),
                description="Branch plan",
                file=SimpleUploadedFile("div-wa.txt", b"d", content_type="text/plain"),
                original_filename="div-wa.txt",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_division_uploaded_documents_report",
                    kwargs={"division_pk": self.division.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "div-doc.pdf")
            self.assertContains(response, "div-wa.txt")
            self.assertNotContains(response, "eng-doc.pdf")
            self.assertNotContains(response, "eng-wa.txt")

    def test_report_flags_duplicates_and_allows_delete(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            first = DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 5),
                description="Branch plan",
                file=SimpleUploadedFile("dup.txt", b"d1", content_type="text/plain"),
                original_filename="dup.txt",
                created_by=self.user,
            )
            second = DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 5),
                description="Branch plan",
                file=SimpleUploadedFile("dup.txt", b"d2", content_type="text/plain"),
                original_filename="dup.txt",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_uploaded_documents_report",
                    kwargs={"engagement_pk": self.engagement.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "2x")

            delete_response = self.client.post(
                reverse(
                    "engagement_uploaded_documents_report",
                    kwargs={"engagement_pk": self.engagement.pk},
                ),
                {
                    "action": "delete_duplicate",
                    "source_kind": "division_work_area_doc",
                    "pk": str(second.pk),
                },
            )
            self.assertEqual(delete_response.status_code, 302)
            self.assertTrue(
                DivisionWorkAreaDocument.objects.filter(pk=first.pk).exists()
            )
            self.assertFalse(
                DivisionWorkAreaDocument.objects.filter(pk=second.pk).exists()
            )

    def test_division_report_flags_duplicates_and_allows_delete(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            first = EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_map,
                file=SimpleUploadedFile("dup-div.pdf", b"a1", content_type="application/pdf"),
                original_filename="dup-div.pdf",
                document_date=date(2044, 5, 3),
                created_by=self.user,
            )
            second = EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_map,
                file=SimpleUploadedFile("dup-div.pdf", b"a2", content_type="application/pdf"),
                original_filename="dup-div.pdf",
                document_date=date(2044, 5, 3),
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_division_uploaded_documents_report",
                    kwargs={"division_pk": self.division.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "2x")

            delete_response = self.client.post(
                reverse(
                    "engagement_division_uploaded_documents_report",
                    kwargs={"division_pk": self.division.pk},
                ),
                {
                    "action": "delete_duplicate",
                    "source_kind": "division_attachment",
                    "pk": str(second.pk),
                },
            )
            self.assertEqual(delete_response.status_code, 302)
            self.assertTrue(
                EngagementDivisionDocumentationMapAttachment.objects.filter(
                    pk=first.pk
                ).exists()
            )
            self.assertFalse(
                EngagementDivisionDocumentationMapAttachment.objects.filter(
                    pk=second.pk
                ).exists()
            )

    def test_division_report_flags_duplicates_across_sources(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_map,
                file=SimpleUploadedFile("fin.pdf", b"a1", content_type="application/pdf"),
                original_filename="financial-statements.pdf",
                document_date=date(2044, 5, 3),
                created_by=self.user,
            )
            DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 9),
                description="Financial Statements",
                file=SimpleUploadedFile("fin.pdf", b"a2", content_type="application/pdf"),
                original_filename="financial-statements.pdf",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_division_uploaded_documents_report",
                    kwargs={"division_pk": self.division.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "2x")

    def test_engagement_report_does_not_flag_same_filename_across_divisions(self):
        with override_settings(MEDIA_ROOT=self.media_dir):
            other_division = EngagementDivision.objects.create(
                engagement=self.engagement,
                division_name="Other Branch",
                planned_start=None,
                planned_finish=None,
                created_by=self.user,
            )
            other_div_work_area = DivisionWorkArea.objects.create(
                division=other_division,
                work_area_name="Other Source files",
                sort_order=2,
                created_by=self.user,
            )
            DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2044, 5, 5),
                description="Working paper",
                file=SimpleUploadedFile("same.zip", b"d1", content_type="application/zip"),
                original_filename="same-name.zip",
                created_by=self.user,
            )
            DivisionWorkAreaDocument.objects.create(
                work_area=other_div_work_area,
                document_date=date(2044, 5, 6),
                description="Working paper",
                file=SimpleUploadedFile("same.zip", b"d2", content_type="application/zip"),
                original_filename="same-name.zip",
                created_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(
                reverse(
                    "engagement_uploaded_documents_report",
                    kwargs={"engagement_pk": self.engagement.pk},
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "2x")


class EngagementWorkAreaTeamAssignmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="wa_assign_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="WA Assign Corp",
            client_short_name="WAA",
            client_code="WAA1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY43",
            start_date=date(2042, 4, 1),
            end_date=date(2043, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Support",
            service_code="SUPP",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Bank confirmations",
            sort_order=0,
            created_by=self.user,
        )
        self.member = TeamMember.objects.create(
            first_name="Nila",
            last_name="Roy",
            called_as="Nila",
            code="NR01",
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2042, 4, 1),
            planned_finish=date(2043, 3, 31),
            created_by=self.user,
        )

    def test_create_assignment_with_notes(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_work_area_assignment_create",
                args=[self.engagement.pk, self.work_area.pk],
            ),
            {
                "team_member": str(self.member.pk),
                "planned_start": "2042-04-10",
                "planned_finish": "2042-04-20",
                "assignment_notes": "Please prepare and file confirmations.",
            },
        )
        self.assertEqual(response.status_code, 302)
        row = EngagementWorkAreaTeamAssignment.objects.get(
            work_area=self.work_area, team_member=self.member
        )
        self.assertEqual(row.planned_start, date(2042, 4, 10))
        self.assertEqual(row.planned_finish, date(2042, 4, 20))
        self.assertEqual(row.assignment_notes, "Please prepare and file confirmations.")

    def test_planned_dates_are_required(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_work_area_assignment_create",
                args=[self.engagement.pk, self.work_area.pk],
            ),
            {
                "team_member": str(self.member.pk),
                "planned_start": "",
                "planned_finish": "",
                "assignment_notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")

    def test_cannot_assign_member_not_on_engagement_roster(self):
        other = TeamMember.objects.create(
            first_name="Other",
            last_name="Person",
            called_as="Other",
            code="OP99",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_work_area_assignment_create",
                args=[self.engagement.pk, self.work_area.pk],
            ),
            {
                "team_member": str(other.pk),
                "planned_start": "2042-04-10",
                "planned_finish": "2042-04-20",
                "assignment_notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            EngagementWorkAreaTeamAssignment.objects.filter(
                work_area=self.work_area, team_member=other
            ).exists()
        )


class DivisionWorkAreaTeamAssignmentFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="div_wa_form_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Div WA Form Corp",
            client_short_name="DWF",
            client_code="DWF1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY44",
            start_date=date(2043, 4, 1),
            end_date=date(2044, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUDX",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="India",
            created_by=self.user,
        )
        self.work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Schedule verification",
            sort_order=1,
            created_by=self.user,
        )
        self.on_division = TeamMember.objects.create(
            first_name="Jai",
            last_name="R",
            called_as="Jai",
            code="AC03",
            created_by=self.user,
        )
        self.off_division = TeamMember.objects.create(
            first_name="Not",
            last_name="OnDivision",
            called_as="NOD",
            code="NOD1",
            created_by=self.user,
        )
        EngagementDivisionTeamAssignment.objects.create(
            division=self.division,
            team_member=self.on_division,
            planned_start=date(2043, 4, 1),
            planned_finish=date(2044, 3, 31),
            created_by=self.user,
        )

    def test_team_member_choices_limited_to_division_roster(self):
        form = DivisionWorkAreaTeamAssignmentForm(work_area=self.work_area)
        pks = set(form.fields["team_member"].queryset.values_list("pk", flat=True))
        self.assertEqual(pks, {self.on_division.pk})

    def test_cannot_post_member_not_on_division_roster(self):
        form = DivisionWorkAreaTeamAssignmentForm(
            work_area=self.work_area,
            data={
                "team_member": str(self.off_division.pk),
                "planned_start": "2043-05-01",
                "planned_finish": "2043-05-10",
                "assignment_notes": "",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("team_member", form.errors)


class EngagementTeamAssignmentMailTests(TestCase):
    def setUp(self):
        from django.utils import timezone

        self.today = timezone.localdate()
        self.superuser = get_user_model().objects.create_user(
            username="mail_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.normal_user = get_user_model().objects.create_user(
            username="mail_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.superuser},
        )
        self.client_item = Client.objects.create(
            client_name="Mail Corp",
            client_short_name="MC",
            client_code="MC01",
            classification=self.classification,
            is_active=True,
            created_by=self.superuser,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY99",
            start_date=self.today - timedelta(days=500),
            end_date=self.today + timedelta(days=500),
            created_by=self.superuser,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUD",
            created_by=self.superuser,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.superuser,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=self.today - timedelta(days=5),
            planned_finish=self.today + timedelta(days=60),
            created_by=self.superuser,
        )
        self.member = TeamMember.objects.create(
            first_name="Pat",
            last_name="Lee",
            called_as="Pat",
            code="PL01",
            work_email="pat@example.com",
            created_by=self.superuser,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=self.today - timedelta(days=365),
            to_date=None,
            notes="Joined",
            created_by=self.superuser,
        )
        smtp = SmtpMailSettings.get_solo()
        smtp.enabled = True
        smtp.username = "noreply@example.com"
        smtp.password = "app-pass"
        smtp.default_from_email = "noreply@example.com"
        smtp.save()

    def test_mail_settings_forbidden_for_non_superuser(self):
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse("setup_mail_settings"))
        self.assertEqual(response.status_code, 403)

    @patch("engagements.team_mail.send_mail")
    def test_future_assignment_sends_mail_on_create(self, mock_send):
        self.client.force_login(self.superuser)
        url = reverse("engagement_team_assignment_create", args=[self.engagement.pk])
        response = self.client.post(
            url,
            {
                "team_member": str(self.member.pk),
                "planned_start": str(self.today),
                "planned_finish": str(self.today + timedelta(days=10)),
            },
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        assignment = EngagementTeamAssignment.objects.get(
            engagement=self.engagement, team_member=self.member
        )
        self.assertIsNotNone(assignment.notified_at)

    @patch("engagements.team_mail.send_mail")
    def test_past_assignment_does_not_auto_send(self, mock_send):
        self.client.force_login(self.superuser)
        url = reverse("engagement_team_assignment_create", args=[self.engagement.pk])
        past_start = self.today - timedelta(days=3)
        past_end = self.today - timedelta(days=2)
        response = self.client.post(
            url,
            {
                "team_member": str(self.member.pk),
                "planned_start": str(past_start),
                "planned_finish": str(past_end),
            },
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_not_called()
        assignment = EngagementTeamAssignment.objects.get(
            engagement=self.engagement, team_member=self.member
        )
        self.assertIsNone(assignment.notified_at)

    @patch("engagements.team_mail.send_mail")
    def test_manual_send_from_list_for_past_assignment(self, mock_send):
        self.client.force_login(self.superuser)
        assignment = EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=self.today - timedelta(days=20),
            planned_finish=self.today - timedelta(days=10),
            created_by=self.superuser,
        )
        list_url = reverse("engagement_team_assignments", args=[self.engagement.pk])
        response = self.client.post(
            list_url,
            {"action": "send_assignment_mail", "pk": str(assignment.pk)},
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        assignment.refresh_from_db()
        self.assertIsNotNone(assignment.notified_at)


class BulkEngagementTeamAssignmentTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_user(
            username="bulk_assign_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.superuser},
        )
        self.client_item = Client.objects.create(
            client_name="Bulk Assign Corp",
            client_short_name="BAC",
            client_code="BAC1",
            classification=self.classification,
            is_active=True,
            created_by=self.superuser,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY97",
            start_date=date(2096, 4, 1),
            end_date=date(2097, 3, 31),
            created_by=self.superuser,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="BULK",
            created_by=self.superuser,
        )
        self.member = TeamMember.objects.create(
            first_name="Managing",
            last_name="Partner",
            called_as="MP",
            code="MP01",
            created_by=self.superuser,
        )
        self.eng1 = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.superuser,
        )
        self.eng2 = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=Service.objects.create(
                service_desc="Tax",
                service_code="TAXB",
                created_by=self.superuser,
            ),
            created_by=self.superuser,
        )
        self.eng3 = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=Service.objects.create(
                service_desc="Consulting",
                service_code="CONB",
                created_by=self.superuser,
            ),
            created_by=self.superuser,
        )
        EngagementSchedule.objects.create(
            engagement=self.eng1,
            planned_start=date(2096, 4, 5),
            planned_finish=date(2096, 4, 30),
            created_by=self.superuser,
        )
        EngagementSchedule.objects.create(
            engagement=self.eng1,
            planned_start=date(2096, 5, 10),
            planned_finish=date(2096, 5, 20),
            created_by=self.superuser,
        )
        # eng2 intentionally has no schedule (should be skipped)
        EngagementSchedule.objects.create(
            engagement=self.eng3,
            planned_start=date(2096, 4, 1),
            planned_finish=date(2096, 6, 1),
            created_by=self.superuser,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.eng3,
            team_member=self.member,
            planned_start=date(2096, 4, 10),
            planned_finish=date(2096, 4, 25),
            created_by=self.superuser,
        )

    def test_bulk_assign_uses_schedule_bounds_and_skips_invalid(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("bulk_engagement_team_assignments"),
            {
                "team_member_id": str(self.member.pk),
                "engagement_ids": [str(self.eng1.pk), str(self.eng2.pk), str(self.eng3.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        created = EngagementTeamAssignment.objects.get(
            engagement=self.eng1, team_member=self.member
        )
        self.assertEqual(created.planned_start, date(2096, 4, 5))
        self.assertEqual(created.planned_finish, date(2096, 5, 20))
        self.assertFalse(
            EngagementTeamAssignment.objects.filter(
                engagement=self.eng2, team_member=self.member
            ).exists()
        )
        # eng3 remains single row because overlapping assignment already exists
        self.assertEqual(
            EngagementTeamAssignment.objects.filter(
                engagement=self.eng3, team_member=self.member
            ).count(),
            1,
        )


class DivisionWorkAreaConfirmationMailTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_user(
            username="dwa_mail_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.superuser},
        )
        self.client_item = Client.objects.create(
            client_name="Division Mail Corp",
            client_short_name="DMC",
            client_code="DMC1",
            classification=self.classification,
            is_active=True,
            created_by=self.superuser,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY98",
            start_date=date(2097, 4, 1),
            end_date=date(2098, 3, 31),
            created_by=self.superuser,
        )
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUX",
            created_by=self.superuser,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.superuser,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Main",
            created_by=self.superuser,
        )
        self.member = TeamMember.objects.create(
            first_name="Pat",
            last_name="Lee",
            called_as="Pat",
            code="PL02",
            work_email="pat@example.com",
            created_by=self.superuser,
        )
        self.wa1 = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Planning",
            sort_order=1,
            created_by=self.superuser,
        )
        self.wa2 = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Fieldwork",
            sort_order=2,
            created_by=self.superuser,
        )
        self.a1 = DivisionWorkAreaTeamAssignment.objects.create(
            work_area=self.wa1,
            team_member=self.member,
            planned_start=date(2097, 4, 10),
            planned_finish=date(2097, 4, 20),
            created_by=self.superuser,
        )
        self.a2 = DivisionWorkAreaTeamAssignment.objects.create(
            work_area=self.wa2,
            team_member=self.member,
            planned_start=date(2097, 4, 21),
            planned_finish=date(2097, 5, 5),
            created_by=self.superuser,
        )
        smtp = SmtpMailSettings.get_solo()
        smtp.enabled = True
        smtp.username = "noreply@example.com"
        smtp.password = "app-pass"
        smtp.default_from_email = "noreply@example.com"
        smtp.save()

    @patch("engagements.team_mail.send_mail")
    def test_send_confirmation_mail_logs_and_dedupes(self, mock_send):
        self.client.force_login(self.superuser)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.post(url, {"action": "send_confirmation_mail"})
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        self.assertEqual(
            DivisionWorkAreaConfirmationMailLog.objects.filter(
                assignment_id__in=[self.a1.pk, self.a2.pk]
            ).count(),
            2,
        )

        response = self.client.post(url, {"action": "send_confirmation_mail"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(
            DivisionWorkAreaConfirmationMailLog.objects.filter(
                assignment_id__in=[self.a1.pk, self.a2.pk]
            ).count(),
            2,
        )


class EngagementWorkAreaFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="wa_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="WA Corp",
            client_short_name="WA",
            client_code="WA01",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY32",
            start_date=date(2031, 4, 1),
            end_date=date(2032, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Advisory",
            service_code="ADVY",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Working paper",
            document_stage=EngagementDocumentation.ENGAGEMENT_WORKING_PAPERS,
            created_by=self.user,
        )

    def test_work_area_name_trimmed(self):
        form = EngagementWorkAreaForm(
            data={
                "work_area_name": "  Fieldwork  ",
                "documentation": str(self.documentation.pk),
                "sort_order": "1",
            },
            engagement=self.engagement,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["work_area_name"], "Fieldwork")

    def test_documentation_is_required(self):
        form = EngagementWorkAreaForm(
            data={"work_area_name": "Fieldwork", "sort_order": "1"},
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_duplicate_work_area_name_rejected(self):
        EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Planning",
            sort_order=0,
            created_by=self.user,
        )
        form = EngagementWorkAreaForm(
            data={
                "work_area_name": "Planning",
                "documentation": str(self.documentation.pk),
                "sort_order": "2",
            },
            engagement=self.engagement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("work_area_name", form.errors)

    def test_sort_order_defaults_to_next_value(self):
        EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Planning",
            sort_order=3,
            created_by=self.user,
        )
        EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Execution",
            sort_order=7,
            created_by=self.user,
        )

        form = EngagementWorkAreaForm(engagement=self.engagement)

        self.assertEqual(form.fields["sort_order"].initial, 8)


class EngagementWorkAreaFromServiceTemplateTests(TestCase):
    """Pick standard service work areas (checkboxes) onto engagement / division."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="wa_tpl_admin",
            email="wa_tpl_admin@example.com",
            password="pass12345",
        )
        self.regular = get_user_model().objects.create_user(
            username="wa_tpl_reg",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.admin},
        )
        self.client_item = Client.objects.create(
            client_name="Tpl Corp",
            client_short_name="TPC",
            client_code="TPC1",
            classification=self.classification,
            is_active=True,
            created_by=self.admin,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY90",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.admin,
        )
        self.service = Service.objects.create(
            service_desc="Statutory",
            service_code="STAT",
            created_by=self.admin,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.admin,
        )
        self.tpl_a = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Revenue",
            sort_order=1,
            created_by=self.admin,
        )
        self.tpl_b = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Expenses",
            sort_order=2,
            created_by=self.admin,
        )
        ServiceEngagementChecklistItem.objects.create(
            work_area=self.tpl_a,
            line_text="Revenue line",
            sort_order=1,
            created_by=self.admin,
        )
        ServiceEngagementChecklistItem.objects.create(
            work_area=self.tpl_b,
            line_text="Expenses line",
            sort_order=1,
            created_by=self.admin,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Main",
            created_by=self.admin,
        )

    def test_engagement_get_lists_templates(self):
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Standard work areas for this service")
        self.assertContains(response, "Revenue")
        self.assertContains(response, "Expenses")
        self.assertContains(response, "(1 checklist line)")
        self.assertContains(response, "Select all")
        self.assertContains(response, "Clear all")

    def test_engagement_picker_disables_templates_with_no_checklist_lines(self):
        empty_tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Empty area",
            sort_order=3,
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empty area")
        self.assertContains(response, "(0 checklist lines)")
        self.assertContains(response, f'value="{empty_tpl.pk}"')
        self.assertContains(response, "disabled")

        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(empty_tpl.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            EngagementWorkArea.objects.filter(
                engagement=self.engagement,
                service_checklist_work_area=empty_tpl,
            ).exists()
        )

    def test_engagement_post_adds_selected_and_skips_duplicate(self):
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(self.tpl_a.pk), str(self.tpl_b.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            EngagementWorkArea.objects.filter(engagement=self.engagement).count(), 2
        )
        row_a = EngagementWorkArea.objects.get(
            engagement=self.engagement, service_checklist_work_area=self.tpl_a
        )
        self.assertEqual(row_a.work_area_name, "Revenue")

        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(self.tpl_a.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            EngagementWorkArea.objects.filter(engagement=self.engagement).count(), 2
        )

    def test_after_adding_all_templates_picker_shows_complete_message(self):
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(self.tpl_a.pk), str(self.tpl_b.pk)],
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "All standard work areas for this service are already on this engagement.",
        )
        self.assertNotContains(response, "Add selected to engagement")

    def test_non_superuser_cannot_bulk_add(self):
        g, _ = Group.objects.get_or_create(name="module_engagements")
        self.regular.groups.add(g)
        member = TeamMember.objects.create(
            first_name="Reg",
            last_name="User",
            called_as="Reg",
            code="WT90",
            user=self.regular,
            created_by=self.admin,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=member,
            planned_start=date(2026, 4, 1),
            planned_finish=date(2027, 3, 31),
            created_by=self.admin,
        )
        self.client.force_login(self.regular)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(self.tpl_a.pk)],
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            EngagementWorkArea.objects.filter(engagement=self.engagement).exists()
        )

    def test_division_get_lists_templates_with_line_counts(self):
        self.client.force_login(self.admin)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revenue")
        self.assertContains(response, "(1 checklist line)")
        self.assertContains(response, "Select all")
        self.assertContains(response, "Clear all")

    def test_division_picker_disables_templates_with_no_checklist_lines(self):
        empty_tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Empty division area",
            sort_order=3,
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empty division area")
        self.assertContains(response, "(0 checklist lines)")
        self.assertContains(response, f'value="{empty_tpl.pk}"')
        self.assertContains(response, "disabled")

        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(empty_tpl.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DivisionWorkArea.objects.filter(
                division=self.division,
                service_checklist_work_area=empty_tpl,
            ).exists()
        )

    def test_division_post_adds_selected(self):
        self.client.force_login(self.admin)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.post(
            url,
            {
                "action": "add_from_service_templates",
                "service_work_area_ids": [str(self.tpl_a.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        dwa = DivisionWorkArea.objects.get(division=self.division)
        self.assertEqual(dwa.work_area_name, "Revenue")
        self.assertEqual(dwa.service_checklist_work_area_id, self.tpl_a.pk)

    def test_engagement_bulk_add_all_json(self):
        import json

        empty_tpl = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="No lines WA",
            sort_order=9,
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.post(
            url,
            {"action": "bulk_add_all_standard"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["work_areas_added"], 2)
        self.assertEqual(data["checklist_lines_added"], 2)
        self.assertFalse(
            EngagementWorkArea.objects.filter(
                engagement=self.engagement,
                service_checklist_work_area=empty_tpl,
            ).exists()
        )
        wa_a = EngagementWorkArea.objects.get(
            engagement=self.engagement, service_checklist_work_area=self.tpl_a
        )
        self.assertEqual(
            AuditQuery.objects.filter(engagement_work_area=wa_a).count(), 1
        )

    def test_engagement_bulk_delete_all_skips_work_areas_with_queries(self):
        import json

        wa_a = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Has notes",
            sort_order=1,
            created_by=self.admin,
        )
        EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="No notes",
            sort_order=2,
            created_by=self.admin,
        )
        AuditQuery.objects.create(
            engagement_work_area=wa_a,
            query_date=date(2026, 5, 22),
            subject="Q",
            query_text="Note",
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        url = reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk})
        response = self.client.post(
            url,
            {"action": "bulk_delete_all_without_queries"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["deleted"], 1)
        self.assertEqual(data["skipped_with_queries"], 1)
        self.assertTrue(EngagementWorkArea.objects.filter(pk=wa_a.pk).exists())
        self.assertEqual(
            EngagementWorkArea.objects.filter(engagement=self.engagement).count(), 1
        )

    def test_division_bulk_add_all_json(self):
        import json

        self.client.force_login(self.admin)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.post(
            url,
            {"action": "bulk_add_all_standard"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["work_areas_added"], 2)
        self.assertEqual(data["checklist_lines_added"], 2)

    def test_division_bulk_delete_all_skips_work_areas_with_queries(self):
        import json

        wa = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Div notes",
            sort_order=1,
            created_by=self.admin,
        )
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Div empty",
            sort_order=2,
            created_by=self.admin,
        )
        AuditQuery.objects.create(
            division_work_area=wa,
            query_date=date(2026, 5, 22),
            subject="Q",
            query_text="Note",
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        url = reverse("engagement_division_work_areas", args=[self.division.pk])
        response = self.client.post(
            url,
            {"action": "bulk_delete_all_without_queries"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["deleted"], 1)
        self.assertEqual(data["skipped_with_queries"], 1)


class DivisionWorkAreaFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dwa_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="DWA Corp",
            client_short_name="DWA",
            client_code="DWA1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY33",
            start_date=date(2032, 4, 1),
            end_date=date(2033, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Consulting",
            service_code="CONS",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="North",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Working paper",
            document_stage=EngagementDocumentation.ENGAGEMENT_WORKING_PAPERS,
            created_by=self.user,
        )

    def test_division_work_area_name_trimmed(self):
        form = DivisionWorkAreaForm(
            data={
                "work_area_name": "  Inventory  ",
                "documentation": str(self.documentation.pk),
                "sort_order": "0",
            },
            division=self.division,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["work_area_name"], "Inventory")

    def test_documentation_is_required(self):
        form = DivisionWorkAreaForm(
            data={"work_area_name": "Inventory", "sort_order": "0"},
            division=self.division,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("documentation", form.errors)

    def test_duplicate_division_work_area_name_rejected(self):
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Cash",
            sort_order=0,
            created_by=self.user,
        )
        form = DivisionWorkAreaForm(
            data={
                "work_area_name": "Cash",
                "documentation": str(self.documentation.pk),
                "sort_order": "1",
            },
            division=self.division,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("work_area_name", form.errors)

    def test_sort_order_defaults_to_next_value(self):
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Cash",
            sort_order=2,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Receivables",
            sort_order=5,
            created_by=self.user,
        )

        form = DivisionWorkAreaForm(division=self.division)

        self.assertEqual(form.fields["sort_order"].initial, 6)


class EngagementWorkAreaPeriodFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="wap_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="WAP Corp",
            client_short_name="WAP",
            client_code="WAP1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY34",
            start_date=date(2033, 4, 1),
            end_date=date(2034, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Compliance",
            service_code="COMP",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2033, 4, 5),
            planned_finish=date(2033, 4, 25),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Revenue testing",
            sort_order=0,
            created_by=self.user,
        )

    def test_schedule_row_planned_within_engagement_schedule(self):
        form = EngagementWorkAreaPeriodForm(
            data={
                "planned_start": "2033-04-10",
                "planned_finish": "2033-04-20",
                "actual_start": "",
                "actual_finish": "",
            },
            work_area=self.work_area,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_schedule_row_planned_outside_schedule_rejected(self):
        form = EngagementWorkAreaPeriodForm(
            data={
                "planned_start": "2033-04-01",
                "planned_finish": "2033-04-03",
                "actual_start": "",
                "actual_finish": "",
            },
            work_area=self.work_area,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("planned_start", form.errors)


class EngagementStatusAutoUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="status_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Status Corp",
            client_short_name="Status",
            client_code="STS1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY55",
            start_date=date(2054, 4, 1),
            end_date=date(2055, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Status Audit",
            service_code="STAU",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Status Division",
            planned_start=None,
            planned_finish=None,
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        self.eng_work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Status WA",
            sort_order=1,
            created_by=self.user,
        )
        self.div_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Status Div WA",
            sort_order=1,
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Status Doc",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.documentation.applicable_classifications.add(self.classification)
        self.div_doc_map = EngagementDivisionDocumentationMap.objects.create(
            division=self.division,
            documentation=self.documentation,
            created_by=self.user,
        )
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_engagement_status_transitions(self):
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "Pending")

        schedule = EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2054, 4, 10),
            planned_finish=date(2054, 4, 25),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "Scheduled")

        with override_settings(MEDIA_ROOT=self.media_dir):
            DivisionWorkAreaDocument.objects.create(
                work_area=self.div_work_area,
                document_date=date(2054, 4, 12),
                description="Status file",
                file=SimpleUploadedFile(
                    "status.pdf", b"a", content_type="application/pdf"
                ),
                original_filename="status.pdf",
                created_by=self.user,
            )
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "In Progress")

        schedule.actual_finish = date(2054, 5, 1)
        schedule.save(update_fields=["actual_finish"])
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "Completed")

    def test_division_and_work_area_status_transitions(self):
        self.division.refresh_from_db()
        self.assertEqual(self.division.status, "Pending")
        self.eng_work_area.refresh_from_db()
        self.assertEqual(self.eng_work_area.status, "Pending")

        self.division.planned_finish = date(2054, 4, 30)
        self.division.save(update_fields=["planned_finish"])
        self.division.refresh_from_db()
        self.assertEqual(self.division.status, "Scheduled")

        period = EngagementWorkAreaPeriod.objects.create(
            work_area=self.eng_work_area,
            planned_start=date(2054, 4, 15),
            planned_finish=date(2054, 4, 20),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        self.eng_work_area.refresh_from_db()
        self.assertEqual(self.eng_work_area.status, "Scheduled")

        with override_settings(MEDIA_ROOT=self.media_dir):
            EngagementDivisionDocumentationMapAttachment.objects.create(
                documentation_map=self.div_doc_map,
                file=SimpleUploadedFile(
                    "div-status.pdf", b"a", content_type="application/pdf"
                ),
                original_filename="div-status.pdf",
                document_date=date(2054, 4, 18),
                created_by=self.user,
            )
            EngagementWorkAreaDocument.objects.create(
                work_area=self.eng_work_area,
                document_date=date(2054, 4, 18),
                description="WA status",
                file=SimpleUploadedFile(
                    "wa-status.pdf", b"a", content_type="application/pdf"
                ),
                original_filename="wa-status.pdf",
                created_by=self.user,
            )
        self.division.refresh_from_db()
        self.assertEqual(self.division.status, "In Progress")
        self.eng_work_area.refresh_from_db()
        self.assertEqual(self.eng_work_area.status, "In Progress")

        self.division.actual_finish = date(2054, 5, 3)
        self.division.save(update_fields=["actual_finish"])
        self.division.refresh_from_db()
        self.assertEqual(self.division.status, "Completed")

        period.actual_finish = date(2054, 5, 4)
        period.save(update_fields=["actual_finish"])
        self.eng_work_area.refresh_from_db()
        self.assertEqual(self.eng_work_area.status, "Completed")

    def test_engagement_actual_finish_closes_divisions_and_work_areas(self):
        eng_period = EngagementWorkAreaPeriod.objects.create(
            work_area=self.eng_work_area,
            planned_start=date(2054, 4, 15),
            planned_finish=date(2054, 4, 20),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        div_period = DivisionWorkAreaPeriod.objects.create(
            work_area=self.div_work_area,
            planned_start=date(2054, 4, 16),
            planned_finish=date(2054, 4, 21),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2054, 4, 10),
            planned_finish=date(2054, 4, 25),
            actual_start=date(2054, 4, 10),
            actual_finish=date(2054, 5, 5),
            created_by=self.user,
        )

        self.division.refresh_from_db()
        self.eng_work_area.refresh_from_db()
        self.div_work_area.refresh_from_db()
        eng_period.refresh_from_db()
        div_period.refresh_from_db()

        self.assertEqual(self.division.actual_finish, date(2054, 5, 5))
        self.assertEqual(self.division.status, "Completed")
        self.assertEqual(self.division.closure_source, "engagement_auto_close")
        self.assertEqual(self.eng_work_area.status, "Completed")
        self.assertEqual(self.eng_work_area.closure_source, "engagement_auto_close")
        self.assertEqual(self.div_work_area.status, "Completed")
        self.assertEqual(self.div_work_area.closure_source, "engagement_auto_close")
        self.assertEqual(eng_period.actual_finish, date(2054, 5, 5))
        self.assertEqual(eng_period.closure_source, "engagement_auto_close")
        self.assertEqual(div_period.actual_finish, date(2054, 5, 5))
        self.assertEqual(div_period.closure_source, "engagement_auto_close")

    def test_actual_start_backfill_runs_only_when_engagement_is_closed(self):
        eng_period = EngagementWorkAreaPeriod.objects.create(
            work_area=self.eng_work_area,
            planned_start=date(2054, 4, 15),
            planned_finish=date(2054, 4, 20),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        div_period = DivisionWorkAreaPeriod.objects.create(
            work_area=self.div_work_area,
            planned_start=date(2054, 4, 16),
            planned_finish=date(2054, 4, 21),
            actual_start=None,
            actual_finish=None,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2054, 4, 10),
            planned_finish=date(2054, 4, 25),
            actual_start=date(2054, 4, 11),
            actual_finish=None,
            created_by=self.user,
        )
        self.division.refresh_from_db()
        eng_period.refresh_from_db()
        div_period.refresh_from_db()
        self.assertIsNone(self.division.actual_start)
        self.assertIsNone(eng_period.actual_start)
        self.assertIsNone(div_period.actual_start)

        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2054, 4, 26),
            planned_finish=date(2054, 5, 2),
            actual_start=None,
            actual_finish=date(2054, 5, 5),
            created_by=self.user,
        )

        self.division.refresh_from_db()
        eng_period.refresh_from_db()
        div_period.refresh_from_db()

        self.assertEqual(self.division.actual_start, date(2054, 4, 11))
        self.assertEqual(eng_period.actual_start, date(2054, 4, 11))
        self.assertEqual(div_period.actual_start, date(2054, 4, 11))


class WorkAreaPlanReverseUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="wa_reverse_user",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Reverse Corp",
            client_short_name="Rev",
            client_code="RV01",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY42",
            start_date=date(2041, 4, 1),
            end_date=date(2042, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Taxation Services",
            service_code="TAX2",
            created_by=self.user,
        )
        self.documentation = EngagementDocumentation.objects.create(
            standard_document="Work area doc",
            document_stage=EngagementDocumentation.PRE_ENGAGEMENT,
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="ITR Filing",
            sort_order=0,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Branch X",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.division_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Division ITR",
            sort_order=0,
            created_by=self.user,
        )

        assign_user_to_engagement(self.user, self.engagement)

    def test_engagement_work_area_create_backfills_engagement_schedule(self):
        self.client.force_login(self.user)
        self.assertEqual(self.engagement.schedules.count(), 0)
        response = self.client.post(
            reverse(
                "engagement_work_area_schedule_create",
                args=[self.engagement.pk, self.work_area.pk],
            ),
            {
                "planned_start": "2041-12-15",
                "planned_finish": "2041-12-31",
                "actual_start": "",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.engagement.schedules.count(), 1)
        schedule = self.engagement.schedules.first()
        self.assertEqual(schedule.planned_start, date(2041, 12, 15))
        self.assertEqual(schedule.planned_finish, date(2041, 12, 31))

    def test_division_work_area_create_backfills_engagement_schedule(self):
        self.client.force_login(self.user)
        self.assertEqual(self.engagement.schedules.count(), 0)
        response = self.client.post(
            reverse(
                "engagement_division_work_area_schedule_create",
                args=[self.division.pk, self.division_work_area.pk],
            ),
            {
                "planned_start": "2041-11-01",
                "planned_finish": "2041-11-20",
                "actual_start": "",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.engagement.schedules.count(), 1)
        schedule = self.engagement.schedules.first()
        self.assertEqual(schedule.planned_start, date(2041, 11, 1))
        self.assertEqual(schedule.planned_finish, date(2041, 11, 20))

    def test_schedule_row_planned_dates_may_be_blank(self):
        form = EngagementWorkAreaPeriodForm(
            data={
                "planned_start": "",
                "planned_finish": "",
                "actual_start": "",
                "actual_finish": "",
            },
            work_area=self.work_area,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_division_work_area_create_resequences_sort_order(self):
        self.client.force_login(self.user)
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Work B",
            sort_order=2,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Work C",
            sort_order=3,
            created_by=self.user,
        )
        response = self.client.post(
            reverse("engagement_division_work_area_create", args=[self.division.pk]),
            {
                "work_area_name": "Inserted Work",
                "sort_order": "3",
                "documentation": self.documentation.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        actual = list(
            DivisionWorkArea.objects.filter(division=self.division)
            .order_by("sort_order", "id")
            .values_list("work_area_name", "sort_order")
        )
        self.assertEqual(
            actual,
            [
                ("Division ITR", 1),
                ("Work B", 2),
                ("Inserted Work", 3),
                ("Work C", 4),
            ],
        )

    def test_division_work_area_edit_resequences_sort_order(self):
        self.client.force_login(self.user)
        work_b = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Work B",
            sort_order=2,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Work C",
            sort_order=3,
            created_by=self.user,
        )
        response = self.client.post(
            reverse(
                "engagement_division_work_area_edit",
                args=[self.division.pk, work_b.pk],
            ),
            {
                "work_area_name": "Work B",
                "sort_order": "3",
                "documentation": self.documentation.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        actual = list(
            DivisionWorkArea.objects.filter(division=self.division)
            .order_by("sort_order", "id")
            .values_list("work_area_name", "sort_order")
        )
        self.assertEqual(
            actual,
            [
                ("Division ITR", 1),
                ("Work C", 2),
                ("Work B", 3),
            ],
        )

    def test_copy_work_areas_from_another_division_adds_missing_items(self):
        self.client.force_login(self.user)
        source_division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Template Division",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=source_division,
            work_area_name="Planning",
            sort_order=1,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=source_division,
            work_area_name="Field Work",
            sort_order=2,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=source_division,
            work_area_name="Finalization",
            sort_order=3,
            created_by=self.user,
        )
        response = self.client.post(
            reverse("engagement_division_work_areas", args=[self.division.pk]),
            {
                "action": "copy_from_division",
                "source_division_id": str(source_division.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        actual = list(
            DivisionWorkArea.objects.filter(division=self.division)
            .order_by("sort_order", "id")
            .values_list("work_area_name", "sort_order")
        )
        self.assertEqual(
            actual,
            [
                ("Division ITR", 1),
                ("Planning", 2),
                ("Field Work", 3),
                ("Finalization", 4),
            ],
        )

    def test_copy_work_areas_from_another_division_skips_existing_names(self):
        self.client.force_login(self.user)
        DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Planning",
            sort_order=2,
            created_by=self.user,
        )
        source_division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Template Division",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=source_division,
            work_area_name="Planning",
            sort_order=1,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=source_division,
            work_area_name="Closure",
            sort_order=2,
            created_by=self.user,
        )
        response = self.client.post(
            reverse("engagement_division_work_areas", args=[self.division.pk]),
            {
                "action": "copy_from_division",
                "source_division_id": str(source_division.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        names = list(
            DivisionWorkArea.objects.filter(division=self.division)
            .order_by("sort_order", "id")
            .values_list("work_area_name", flat=True)
        )
        self.assertEqual(names, ["Division ITR", "Planning", "Closure"])

    def test_source_division_dropdown_only_shows_same_client_service_and_fy(self):
        self.client.force_login(self.user)
        same_service_source = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Same Service Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        other_fy = FiscalYear.objects.create(
            fy_no="FY43",
            start_date=date(2042, 4, 1),
            end_date=date(2043, 3, 31),
            created_by=self.user,
        )
        other_fy_engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=other_fy,
            service=self.service,
            created_by=self.user,
        )
        other_fy_source = EngagementDivision.objects.create(
            engagement=other_fy_engagement,
            division_name="Other FY Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        other_service = Service.objects.create(
            service_desc="Internal Audit",
            service_code="INTA",
            created_by=self.user,
        )
        other_service_engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=other_service,
            created_by=self.user,
        )
        other_service_source = EngagementDivision.objects.create(
            engagement=other_service_engagement,
            division_name="Other Service Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        other_client = Client.objects.create(
            client_name="Different Corp",
            client_short_name="Dif",
            client_code="DIF1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        other_client_engagement = Engagement.objects.create(
            client=other_client,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        other_client_source = EngagementDivision.objects.create(
            engagement=other_client_engagement,
            division_name="Other Client Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("engagement_division_work_areas", args=[self.division.pk])
        )
        self.assertEqual(response.status_code, 200)
        source_ids = {d.pk for d in response.context["source_divisions"]}
        self.assertIn(same_service_source.pk, source_ids)
        self.assertNotIn(other_fy_source.pk, source_ids)
        self.assertNotIn(other_service_source.pk, source_ids)
        self.assertNotIn(other_client_source.pk, source_ids)

    def test_copy_from_different_service_division_is_rejected(self):
        self.client.force_login(self.user)
        other_service = Service.objects.create(
            service_desc="Internal Audit",
            service_code="INTB",
            created_by=self.user,
        )
        other_engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=other_service,
            created_by=self.user,
        )
        disallowed_source = EngagementDivision.objects.create(
            engagement=other_engagement,
            division_name="Disallowed Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=disallowed_source,
            work_area_name="Should Not Copy",
            sort_order=1,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("engagement_division_work_areas", args=[self.division.pk]),
            {
                "action": "copy_from_division",
                "source_division_id": str(disallowed_source.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        names = set(
            DivisionWorkArea.objects.filter(division=self.division).values_list(
                "work_area_name", flat=True
            )
        )
        self.assertNotIn("Should Not Copy", names)

    def test_copy_from_different_fiscal_year_division_is_rejected(self):
        self.client.force_login(self.user)
        other_fy = FiscalYear.objects.create(
            fy_no="FY43",
            start_date=date(2042, 4, 1),
            end_date=date(2043, 3, 31),
            created_by=self.user,
        )
        other_engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=other_fy,
            service=self.service,
            created_by=self.user,
        )
        disallowed_source = EngagementDivision.objects.create(
            engagement=other_engagement,
            division_name="Other FY Template",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        DivisionWorkArea.objects.create(
            division=disallowed_source,
            work_area_name="Should Not Copy FY",
            sort_order=1,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("engagement_division_work_areas", args=[self.division.pk]),
            {
                "action": "copy_from_division",
                "source_division_id": str(disallowed_source.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        names = set(
            DivisionWorkArea.objects.filter(division=self.division).values_list(
                "work_area_name", flat=True
            )
        )
        self.assertNotIn("Should Not Copy FY", names)


class DivisionWorkAreaPeriodFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dwap_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="DWAP Corp",
            client_short_name="DWAP",
            client_code="DWP1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY35",
            start_date=date(2034, 4, 1),
            end_date=date(2035, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Review",
            service_code="REVW",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Branch C",
            planned_start=None,
            planned_finish=None,
            created_by=self.user,
        )
        self.work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Physical verification",
            sort_order=0,
            created_by=self.user,
        )

    def test_schedule_row_planned_dates_may_be_blank(self):
        form = DivisionWorkAreaPeriodForm(
            data={
                "planned_start": "",
                "planned_finish": "",
                "actual_start": "",
                "actual_finish": "",
            },
            work_area=self.work_area,
        )
        self.assertTrue(form.is_valid(), form.errors)


class EngagementsListStatusFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="elist_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="List Filter Corp",
            client_short_name="LFC",
            client_code="LFC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY88",
            start_date=date(2087, 4, 1),
            end_date=date(2088, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="List Audit",
            service_code="LFAU",
            created_by=self.user,
        )
        self.scheduled_eng = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.scheduled_eng,
            planned_start=date(2087, 5, 1),
            planned_finish=date(2087, 5, 15),
            created_by=self.user,
        )
        self.completed_eng = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=Service.objects.create(
                service_desc="List Tax",
                service_code="LFTX",
                created_by=self.user,
            ),
            created_by=self.user,
        )
        EngagementSchedule.objects.create(
            engagement=self.completed_eng,
            planned_start=date(2087, 6, 1),
            planned_finish=date(2087, 6, 10),
            actual_start=date(2087, 6, 2),
            actual_finish=date(2087, 6, 12),
            created_by=self.user,
        )
        g, _ = Group.objects.get_or_create(name="module_engagements")
        self.user.groups.add(g)
        self.list_member = TeamMember.objects.create(
            first_name="Elist",
            last_name="Member",
            called_as="Elist",
            code="EL01",
            user=self.user,
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.scheduled_eng,
            team_member=self.list_member,
            planned_start=date(2087, 4, 1),
            planned_finish=date(2087, 4, 30),
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.completed_eng,
            team_member=self.list_member,
            planned_start=date(2087, 6, 1),
            planned_finish=date(2087, 6, 20),
            created_by=self.user,
        )

    def test_default_list_excludes_completed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("engagements"))
        self.assertEqual(response.status_code, 200)
        service_names = list(
            response.context["engagements"].values_list("service__service_desc", flat=True)
        )
        self.assertIn("List Audit", service_names)
        self.assertNotIn("List Tax", service_names)

    def test_completed_filter_shows_only_completed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("engagements"), {"status": "completed"})
        self.assertEqual(response.status_code, 200)
        service_names = list(
            response.context["engagements"].values_list("service__service_desc", flat=True)
        )
        self.assertIn("List Tax", service_names)
        self.assertNotIn("List Audit", service_names)

    def test_all_filter_shows_both(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("engagements"), {"status": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "List Tax")
        self.assertContains(response, "List Audit")


class ClosedEntityReopenPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reopen_user",
            password="pass12345",
        )
        self.superuser = get_user_model().objects.create_user(
            username="reopen_admin",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.superuser},
        )
        self.client_item = Client.objects.create(
            client_name="Reopen Corp",
            client_short_name="ROP",
            client_code="ROP1",
            classification=self.classification,
            is_active=True,
            created_by=self.superuser,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY66",
            start_date=date(2065, 4, 1),
            end_date=date(2066, 3, 31),
            created_by=self.superuser,
        )
        self.service = Service.objects.create(
            service_desc="Reopen Audit",
            service_code="RPAU",
            created_by=self.superuser,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.superuser,
        )
        self.member = TeamMember.objects.create(
            first_name="Reopen",
            last_name="User",
            called_as="Reopen",
            code="RP01",
            user=self.user,
            created_by=self.superuser,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2065, 5, 1),
            planned_finish=date(2065, 5, 20),
            created_by=self.superuser,
        )
        self.engagement_schedule = EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2065, 5, 1),
            planned_finish=date(2065, 5, 20),
            actual_start=date(2065, 5, 2),
            actual_finish=date(2065, 5, 22),
            created_by=self.superuser,
        )
        self.division = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Division A",
            planned_start=date(2065, 5, 1),
            planned_finish=date(2065, 5, 20),
            actual_start=date(2065, 5, 2),
            actual_finish=date(2065, 5, 22),
            created_by=self.superuser,
        )
        self.eng_work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Eng WA",
            sort_order=1,
            created_by=self.superuser,
        )
        self.eng_wa_period = EngagementWorkAreaPeriod.objects.create(
            work_area=self.eng_work_area,
            planned_start=date(2065, 5, 3),
            planned_finish=date(2065, 5, 18),
            actual_start=date(2065, 5, 3),
            actual_finish=date(2065, 5, 22),
            created_by=self.superuser,
        )
        self.div_work_area = DivisionWorkArea.objects.create(
            division=self.division,
            work_area_name="Div WA",
            sort_order=1,
            created_by=self.superuser,
        )
        self.div_wa_period = DivisionWorkAreaPeriod.objects.create(
            work_area=self.div_work_area,
            planned_start=date(2065, 5, 4),
            planned_finish=date(2065, 5, 17),
            actual_start=date(2065, 5, 4),
            actual_finish=date(2065, 5, 22),
            created_by=self.superuser,
        )
        grant_engagements_module_access(self.user)

    def test_non_superuser_cannot_reopen_closed_engagement(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_schedule_edit",
                args=[self.engagement.pk, self.engagement_schedule.pk],
            ),
            {
                "planned_start": "2065-05-01",
                "planned_finish": "2065-05-20",
                "actual_start": "2065-05-02",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.engagement_schedule.refresh_from_db()
        self.assertEqual(self.engagement_schedule.actual_finish, date(2065, 5, 22))

    def test_superuser_can_reopen_closed_engagement(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse(
                "engagement_schedule_edit",
                args=[self.engagement.pk, self.engagement_schedule.pk],
            ),
            {
                "planned_start": "2065-05-01",
                "planned_finish": "2065-05-20",
                "actual_start": "2065-05-02",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.engagement_schedule.refresh_from_db()
        self.assertIsNone(self.engagement_schedule.actual_finish)

    def test_non_superuser_cannot_reopen_closed_division(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("engagement_division_edit", args=[self.division.pk]),
            {
                "engagement": self.engagement.pk,
                "division_name": self.division.division_name,
                "planned_start": "2065-05-01",
                "planned_finish": "2065-05-20",
                "actual_start": "2065-05-02",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.division.refresh_from_db()
        self.assertEqual(self.division.actual_finish, date(2065, 5, 22))

    def test_non_superuser_cannot_reopen_closed_work_area(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_work_area_schedule_edit",
                args=[self.engagement.pk, self.eng_work_area.pk, self.eng_wa_period.pk],
            ),
            {
                "planned_start": "2065-05-03",
                "planned_finish": "2065-05-18",
                "actual_start": "2065-05-03",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.eng_wa_period.refresh_from_db()
        self.assertEqual(self.eng_wa_period.actual_finish, date(2065, 5, 22))

    def test_non_superuser_cannot_reopen_closed_division_work_area(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_division_work_area_schedule_edit",
                args=[self.division.pk, self.div_work_area.pk, self.div_wa_period.pk],
            ),
            {
                "planned_start": "2065-05-04",
                "planned_finish": "2065-05-17",
                "actual_start": "2065-05-04",
                "actual_finish": "",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.div_wa_period.refresh_from_db()
        self.assertEqual(self.div_wa_period.actual_finish, date(2065, 5, 22))


class EngagementAssignmentVisibilityTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="assign_admin",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.user = get_user_model().objects.create_user(
            username="assigned_user",
            password="pass12345",
        )
        self.user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.admin},
        )
        self.client_item = Client.objects.create(
            client_name="Visibility Corp",
            client_short_name="Vis",
            client_code="VIS1",
            classification=self.classification,
            is_active=True,
            created_by=self.admin,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY91",
            start_date=date(2090, 4, 1),
            end_date=date(2091, 3, 31),
            created_by=self.admin,
        )
        self.service = Service.objects.create(
            service_desc="Visibility Audit",
            service_code="VISA",
            created_by=self.admin,
        )
        self.eng_allowed = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.admin,
        )
        self.eng_blocked = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=Service.objects.create(
                service_desc="Blocked Service",
                service_code="BLKD",
                created_by=self.admin,
            ),
            created_by=self.admin,
        )
        self.member = TeamMember.objects.create(
            first_name="Assigned",
            last_name="User",
            called_as="Assigned",
            code="AS01",
            user=self.user,
            created_by=self.admin,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.eng_allowed,
            team_member=self.member,
            planned_start=date(2090, 5, 1),
            planned_finish=date(2090, 5, 20),
            created_by=self.admin,
        )
        self.allowed_schedule = EngagementSchedule.objects.create(
            engagement=self.eng_allowed,
            planned_start=date(2090, 5, 1),
            planned_finish=date(2090, 5, 20),
            created_by=self.admin,
        )
        self.blocked_schedule = EngagementSchedule.objects.create(
            engagement=self.eng_blocked,
            planned_start=date(2090, 6, 1),
            planned_finish=date(2090, 6, 20),
            created_by=self.admin,
        )

    def test_non_superuser_list_shows_only_assigned_engagements(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("engagements"), {"status": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility Audit")
        self.assertNotContains(response, "Blocked Service")

    def test_non_superuser_cannot_open_unassigned_engagement_schedule(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("engagement_schedules", args=[self.eng_blocked.pk])
        )
        self.assertEqual(response.status_code, 404)
        allowed_response = self.client.get(
            reverse("engagement_schedules", args=[self.eng_allowed.pk])
        )
        self.assertEqual(allowed_response.status_code, 200)

    def test_non_superuser_cannot_create_engagement_master(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("engagement_create"))
        self.assertEqual(response.status_code, 403)

    def test_non_superuser_can_only_update_actual_dates_not_planned(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "engagement_schedule_edit",
                args=[self.eng_allowed.pk, self.allowed_schedule.pk],
            ),
            {
                "planned_start": "2090-07-01",
                "planned_finish": "2090-07-30",
                "actual_start": "2090-05-02",
                "actual_finish": "2090-05-25",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.allowed_schedule.refresh_from_db()
        self.assertEqual(self.allowed_schedule.planned_start, date(2090, 5, 1))
        self.assertEqual(self.allowed_schedule.planned_finish, date(2090, 5, 20))
        self.assertEqual(self.allowed_schedule.actual_start, date(2090, 5, 2))
        self.assertEqual(self.allowed_schedule.actual_finish, date(2090, 5, 25))

    def test_division_work_area_assignment_limits_visible_work_areas(self):
        limited_user = get_user_model().objects.create_user(
            username="wa_limited_user",
            password="pass12345",
        )
        limited_user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        limited_member = TeamMember.objects.create(
            first_name="WA",
            last_name="Only",
            called_as="WA",
            code="WA01",
            user=limited_user,
            created_by=self.admin,
        )
        division = EngagementDivision.objects.create(
            engagement=self.eng_allowed,
            division_name="Restricted Division",
            created_by=self.admin,
        )
        allowed_work_area = DivisionWorkArea.objects.create(
            division=division,
            work_area_name="Allowed Area",
            sort_order=1,
            created_by=self.admin,
        )
        DivisionWorkArea.objects.create(
            division=division,
            work_area_name="Blocked Area",
            sort_order=2,
            created_by=self.admin,
        )
        DivisionWorkAreaTeamAssignment.objects.create(
            work_area=allowed_work_area,
            team_member=limited_member,
            planned_start=date(2090, 5, 1),
            planned_finish=date(2090, 5, 20),
            created_by=self.admin,
        )

        self.client.force_login(limited_user)
        response = self.client.get(
            reverse("engagement_division_work_areas", args=[division.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Allowed Area")
        self.assertNotContains(response, "Blocked Area")


class TimeSessionStartStopTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="timer_admin",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.user = get_user_model().objects.create_user(
            username="timer_user",
            password="pass12345",
        )
        self.user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.admin},
        )
        client_item = Client.objects.create(
            client_name="Timer Corp",
            client_short_name="Timer",
            client_code="TIM1",
            classification=classification,
            is_active=True,
            created_by=self.admin,
        )
        fy = FiscalYear.objects.create(
            fy_no="FY92",
            start_date=date(2091, 4, 1),
            end_date=date(2092, 3, 31),
            created_by=self.admin,
        )
        self.service_allowed = Service.objects.create(
            service_desc="Timer Allowed",
            service_code="TMRA",
            created_by=self.admin,
        )
        service_blocked = Service.objects.create(
            service_desc="Timer Blocked",
            service_code="TMRB",
            created_by=self.admin,
        )
        self.eng_allowed = Engagement.objects.create(
            client=client_item,
            fiscal_year=fy,
            service=self.service_allowed,
            created_by=self.admin,
        )
        self.eng_blocked = Engagement.objects.create(
            client=client_item,
            fiscal_year=fy,
            service=service_blocked,
            created_by=self.admin,
        )
        member = TeamMember.objects.create(
            first_name="Timer",
            last_name="User",
            called_as="Timer",
            code="TM01",
            user=self.user,
            created_by=self.admin,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.eng_allowed,
            team_member=member,
            planned_start=date(2091, 5, 1),
            planned_finish=date(2091, 5, 20),
            created_by=self.admin,
        )

    def test_start_timer_creates_open_session(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("timer_start_engagement", args=[self.eng_allowed.pk]),
            {"next": reverse("engagements"), "task": "  Field work  "},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeSession.objects.count(), 1)
        session = TimeSession.objects.get()
        self.assertEqual(session.engagement_id, self.eng_allowed.pk)
        self.assertIsNone(session.ended_at)
        self.assertEqual(session.status, "open")
        self.assertEqual(session.task_description, "Field work")

    def test_stop_timer_saves_task_from_post(self):
        self.client.force_login(self.user)
        self.client.post(reverse("timer_start_engagement", args=[self.eng_allowed.pk]))
        session = TimeSession.objects.get()
        self.assertEqual(session.task_description, "")
        self.client.post(reverse("timer_stop"), {"task": "Closing notes"})
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(session.task_description, "Closing notes")

    def test_start_timer_switches_existing_open_session(self):
        second_engagement = Engagement.objects.create(
            client=self.eng_allowed.client,
            fiscal_year=self.eng_allowed.fiscal_year,
            service=Service.objects.create(
                service_desc="Timer Second",
                service_code="TMR2",
                created_by=self.admin,
            ),
            created_by=self.admin,
        )
        EngagementTeamAssignment.objects.create(
            engagement=second_engagement,
            team_member=TeamMember.objects.get(user=self.user),
            planned_start=date(2091, 5, 2),
            planned_finish=date(2091, 5, 21),
            created_by=self.admin,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("timer_start_engagement", args=[self.eng_allowed.pk]))
        response = self.client.post(reverse("timer_start_engagement", args=[second_engagement.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeSession.objects.count(), 2)
        first = TimeSession.objects.order_by("id").first()
        second = TimeSession.objects.order_by("-id").first()
        self.assertIsNotNone(first.ended_at)
        self.assertEqual(first.close_source, "auto_switch")
        self.assertIsNone(second.ended_at)
        self.assertEqual(second.engagement_id, second_engagement.pk)

    def test_start_timer_on_unassigned_engagement_is_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("timer_start_engagement", args=[self.eng_blocked.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(TimeSession.objects.count(), 0)

    def test_my_time_log_lists_sessions(self):
        member = TeamMember.objects.get(user=self.user)
        TimeSession.objects.create(
            team_member=member,
            started_by=self.user,
            engagement=self.eng_allowed,
            started_at=timezone.now() - timedelta(minutes=30),
            ended_at=timezone.now() - timedelta(minutes=10),
            duration_minutes=20,
            status=TIME_SESSION_STATUS_CLOSED,
            close_source="user_stop",
            task_description="Client call",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_time_log"), {"range": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20")
        self.assertContains(response, "Closed")
        self.assertContains(response, "Client call")

    def test_my_time_log_forbidden_without_module(self):
        bare = get_user_model().objects.create_user(
            username="no_mod_time_log",
            password="pass12345",
        )
        self.client.force_login(bare)
        response = self.client.get(reverse("my_time_log"))
        self.assertEqual(response.status_code, 403)

    def test_timer_recent_tasks_returns_tasks_for_engagement_scope(self):
        member = TeamMember.objects.get(user=self.user)
        now = timezone.now()
        TimeSession.objects.create(
            team_member=member,
            started_by=self.user,
            engagement=self.eng_allowed,
            started_at=now - timedelta(hours=1),
            ended_at=now - timedelta(minutes=30),
            duration_minutes=30,
            status=TIME_SESSION_STATUS_CLOSED,
            close_source="user_stop",
            task_description="Field visit",
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("timer_recent_tasks"),
            {"engagement": self.eng_allowed.pk},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["tasks"], ["Field visit"])

    def test_timer_recent_tasks_excludes_other_engagement(self):
        member = TeamMember.objects.get(user=self.user)
        now = timezone.now()
        TimeSession.objects.create(
            team_member=member,
            started_by=self.user,
            engagement=self.eng_allowed,
            started_at=now - timedelta(hours=2),
            ended_at=now - timedelta(hours=1),
            duration_minutes=60,
            status=TIME_SESSION_STATUS_CLOSED,
            close_source="user_stop",
            task_description="Our task",
        )
        second_engagement = Engagement.objects.create(
            client=self.eng_allowed.client,
            fiscal_year=self.eng_allowed.fiscal_year,
            service=Service.objects.create(
                service_desc="Other Svc",
                service_code="OTH1",
                created_by=self.admin,
            ),
            created_by=self.admin,
        )
        EngagementTeamAssignment.objects.create(
            engagement=second_engagement,
            team_member=member,
            planned_start=date(2091, 6, 1),
            planned_finish=date(2091, 6, 20),
            created_by=self.admin,
        )
        TimeSession.objects.create(
            team_member=member,
            started_by=self.user,
            engagement=second_engagement,
            started_at=now - timedelta(minutes=10),
            ended_at=now,
            duration_minutes=10,
            status=TIME_SESSION_STATUS_CLOSED,
            close_source="user_stop",
            task_description="Their task",
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("timer_recent_tasks"),
            {"engagement": self.eng_allowed.pk},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["tasks"], ["Our task"])

    def test_timer_recent_tasks_missing_scope_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("timer_recent_tasks"))
        self.assertEqual(response.status_code, 400)

    def test_timer_recent_tasks_unknown_engagement_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("timer_recent_tasks"),
            {"engagement": 999_999},
        )
        self.assertEqual(response.status_code, 404)

    def test_timer_recent_tasks_forbidden_without_module(self):
        bare = get_user_model().objects.create_user(
            username="no_mod_recent_tasks",
            password="pass12345",
        )
        self.client.force_login(bare)
        response = self.client.get(
            reverse("timer_recent_tasks"),
            {"engagement": self.eng_allowed.pk},
        )
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertEqual(data["tasks"], [])


class ServiceEngagementChecklistPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="cl_su",
            email="cl_su@example.com",
            password="pass12345",
        )
        self.no_access = User.objects.create_user(
            username="cl_no",
            password="pass12345",
        )
        g, _ = Group.objects.get_or_create(name="module_engagements")
        self.eng_user = User.objects.create_user(
            username="cl_eng",
            password="pass12345",
        )
        self.eng_user.groups.add(g)
        self.service = Service.objects.create(
            service_desc="Audit",
            service_code="AUD",
            created_by=self.admin,
        )
        self.url = reverse("engagement_checklist_templates")

    def test_anonymous_redirects(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_no_module_forbidden(self):
        self.client.force_login(self.no_access)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_engagements_module_renders_page(self):
        self.client.force_login(self.eng_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Statutory Audit Check List")

    def test_new_work_area_screen(self):
        self.client.force_login(self.eng_user)
        url = f"{self.url}?service={self.service.pk}&work_area=new"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New work area")

    def test_add_work_area_post(self):
        self.client.force_login(self.eng_user)
        response = self.client.post(
            self.url,
            {
                "service_id": str(self.service.pk),
                "action": "add_work_area",
                "work_area_name": "Fieldwork",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ServiceEngagementChecklistWorkArea.objects.filter(
                service=self.service,
                name="Fieldwork",
            ).exists()
        )

    def test_add_item_post(self):
        wa = ServiceEngagementChecklistWorkArea.objects.create(
            service=self.service,
            name="Planning",
            sort_order=1,
            created_by=self.admin,
        )
        self.client.force_login(self.eng_user)
        response = self.client.post(
            self.url,
            {
                "service_id": str(self.service.pk),
                "action": "add_item",
                "work_area_id": str(wa.pk),
                "item_line": "Confirm scope with client",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ServiceEngagementChecklistItem.objects.filter(
                work_area=wa,
                line_text="Confirm scope with client",
            ).exists()
        )


class EngagementDocumentsAndNotesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="docs_notes_admin",
            password="pass12345",
            email="docs_notes@example.com",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Combined Corp",
            client_short_name="Combined",
            client_code="CMB1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY55",
            start_date=date(2054, 4, 1),
            end_date=date(2055, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Combined Audit",
            service_code="CMBA",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.work_area = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Combined WA",
            sort_order=1,
            created_by=self.user,
        )
        self.query = AuditQuery.objects.create(
            engagement_work_area=self.work_area,
            query_date=date(2054, 6, 1),
            entry_type=AuditQuery.ENTRY_TYPE_REMARK,
            subject="Combined remark",
            query_text="Remark text",
            status=AuditQuery.STATUS_CLOSED,
            created_by=self.user,
        )
        self.document = EngagementWorkAreaDocument.objects.create(
            work_area=self.work_area,
            document_date=date(2054, 6, 2),
            description="Working paper",
            document_reference_no="REF-77",
            file=SimpleUploadedFile("combined.txt", b"x"),
            original_filename="combined.txt",
            created_by=self.user,
        )

    def test_combined_page_shows_notes_and_documents(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "engagement_documents_and_notes",
                kwargs={"engagement_pk": self.engagement.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Combined remark")
        self.assertContains(response, "combined.txt")
        self.assertContains(response, "REF-77")


class SessionEngagementContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="session_eng_admin",
            password="pass12345",
            email="session@example.com",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_a = Client.objects.create(
            client_name="Alpha Corp Limited",
            client_short_name="Alpha Corp",
            client_code="ALP1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.client_b = Client.objects.create(
            client_name="Beta Corp Limited",
            client_short_name="Beta Corp",
            client_code="BET1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY30",
            start_date=date(2029, 4, 1),
            end_date=date(2030, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="STAU",
            created_by=self.user,
        )
        self.engagement_a = Engagement.objects.create(
            client=self.client_a,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.engagement_b = Engagement.objects.create(
            client=self.client_b,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_set_and_clear_session_engagement(self):
        response = self.client.post(
            reverse("session_engagement_set"),
            {
                "engagement_id": str(self.engagement_a.pk),
                "next": reverse("manage_engagements"),
            },
        )
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        session.load()
        self.assertEqual(session["session_engagement_id"], self.engagement_a.pk)

        response = self.client.post(
            reverse("session_engagement_clear"),
            {"next": reverse("manage_engagements")},
        )
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        session.load()
        self.assertNotIn("session_engagement_id", session)

    def test_engagements_list_filtered_by_session(self):
        self.client.post(
            reverse("session_engagement_set"),
            {
                "engagement_id": str(self.engagement_a.pk),
                "next": reverse("engagements"),
            },
        )
        response = self.client.get(reverse("engagements"))
        self.assertEqual(response.status_code, 200)
        engagement_pks = {e.pk for e in response.context["engagements"]}
        self.assertEqual(engagement_pks, {self.engagement_a.pk})

    def test_clear_via_empty_selection(self):
        self.client.post(
            reverse("session_engagement_set"),
            {
                "engagement_id": str(self.engagement_a.pk),
                "next": reverse("engagements"),
            },
        )
        response = self.client.post(
            reverse("session_engagement_set"),
            {"engagement_id": "", "next": reverse("engagements")},
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("engagements"))
        engagement_pks = {e.pk for e in response.context["engagements"]}
        self.assertEqual(engagement_pks, {self.engagement_a.pk, self.engagement_b.pk})
