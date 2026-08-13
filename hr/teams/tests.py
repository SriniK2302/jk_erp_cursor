from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from hr.grades.models import Grade
from hr.qualifications.models import Qualification
from hr.team_grade_maps.forms import TeamGradeMapForm

from .forms import (
    TeamMemberForm,
    TeamMemberQualificationPeriodForm,
    TeamMemberRollPeriodForm,
)
from .models import TeamMember, TeamMemberGradePeriod, TeamMemberRollPeriod


class TeamMemberFormTests(TestCase):
    def test_code_is_trimmed_uppercased_and_limited(self):
        form = TeamMemberForm(
            data={
                "first_name": "Ravi",
                "last_name": "Kumar",
                "called_as": "Ravi",
                "code": " abcd ",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "ABCD")

    def test_common_word_code_is_sanitized(self):
        form = TeamMemberForm(
            data={
                "first_name": "Test",
                "last_name": "User",
                "called_as": "TU",
                "code": "this",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "THIX")


class TeamMemberRollPeriodFormTests(TestCase):
    def test_to_date_cannot_be_before_from_date(self):
        form = TeamMemberRollPeriodForm(
            data={
                "from_date": date(2026, 4, 10),
                "to_date": date(2026, 4, 1),
                "notes": "Exam leave",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("to_date", form.errors)


class TeamMemberQualificationPeriodFormTests(TestCase):
    def test_to_date_cannot_be_before_from_date(self):
        user = get_user_model().objects.create_user(
            username="qual_creator",
            password="pass12345",
        )
        qualification = Qualification.objects.create(
            qualification_desc="Chartered Accountant",
            qualification_code="CA01",
            created_by=user,
        )
        form = TeamMemberQualificationPeriodForm(
            data={
                "qualification": qualification.pk,
                "from_date": date(2026, 4, 10),
                "to_date": date(2026, 4, 1),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("to_date", form.errors)


class TeamGradeMapFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="grade_map_creator",
            password="pass12345",
        )
        self.member = TeamMember.objects.create(
            first_name="Venkateshwaran",
            last_name="Minickam",
            called_as="Venkat",
            code="AC01",
            created_by=self.user,
        )
        self.grade_1 = Grade.objects.create(
            grade_desc="Audit Associate",
            grade_code="AU01",
            created_by=self.user,
        )
        self.grade_2 = Grade.objects.create(
            grade_desc="Audit Manager",
            grade_code="AUMA",
            created_by=self.user,
        )

    def test_requires_on_roll_period(self):
        form = TeamGradeMapForm(
            data={
                "team_member": self.member.pk,
                "grade": self.grade_1.pk,
                "from_date": date(2026, 4, 1),
                "to_date": date(2026, 4, 30),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("team_member", form.errors)

    def test_create_uses_later_of_on_roll_or_last_grade_plus_one(self):
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2026, 4, 1),
            to_date=None,
            notes="",
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=self.grade_1,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 10),
            created_by=self.user,
        )

        form = TeamGradeMapForm(
            data={
                "team_member": self.member.pk,
                "grade": self.grade_2.pk,
                "from_date": date(2026, 4, 2),
                "to_date": None,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["from_date"], date(2026, 4, 11))

    def test_create_keeps_submitted_to_date_when_on_roll_has_end(self):
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            notes="",
            created_by=self.user,
        )

        form = TeamGradeMapForm(
            data={
                "team_member": self.member.pk,
                "grade": self.grade_1.pk,
                "from_date": date(2026, 4, 1),
                "to_date": date(2026, 4, 10),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["to_date"], date(2026, 4, 10))


class TeamGradeMapDefaultsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="defaults_view_user",
            password="pass12345",
        )
        self.client.force_login(self.user)
        self.member = TeamMember.objects.create(
            first_name="Arun",
            last_name="Kumar",
            called_as="Arun",
            code="AR01",
            created_by=self.user,
        )

    def test_returns_derived_defaults(self):
        grade = Grade.objects.create(
            grade_desc="Audit Senior",
            grade_code="AS01",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            notes="",
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=grade,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 10),
            created_by=self.user,
        )

        response = self.client.get(
            reverse("team_grade_map_defaults"),
            {"team_member": self.member.pk},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["from_date"], "2026-04-11")
        self.assertEqual(payload["to_date"], "2026-04-30")
        self.assertFalse(payload["is_to_date_locked"])

    def test_defaults_lock_to_date_when_editing_period_with_successor(self):
        grade_1 = Grade.objects.create(
            grade_desc="Audit Associate",
            grade_code="AU01",
            created_by=self.user,
        )
        grade_2 = Grade.objects.create(
            grade_desc="Audit Manager",
            grade_code="AUMA",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 6, 30),
            notes="",
            created_by=self.user,
        )
        first_period = TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=grade_1,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 10),
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=grade_2,
            from_date=date(2026, 4, 11),
            to_date=None,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("team_grade_map_defaults"),
            {
                "team_member": self.member.pk,
                "period_id": first_period.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_to_date_locked"])
        self.assertEqual(payload["to_date"], "2026-04-10")

    def test_edit_forces_to_date_when_subsequent_grade_exists(self):
        grade_1 = Grade.objects.create(
            grade_desc="Audit Associate",
            grade_code="AU01",
            created_by=self.user,
        )
        grade_2 = Grade.objects.create(
            grade_desc="Audit Manager",
            grade_code="AUMA",
            created_by=self.user,
        )
        TeamMemberRollPeriod.objects.create(
            team_member=self.member,
            from_date=date(2026, 4, 1),
            to_date=None,
            notes="",
            created_by=self.user,
        )
        first_period = TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=grade_1,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 10),
            created_by=self.user,
        )
        TeamMemberGradePeriod.objects.create(
            team_member=self.member,
            grade=grade_2,
            from_date=date(2026, 4, 11),
            to_date=None,
            created_by=self.user,
        )

        form = TeamGradeMapForm(
            data={
                "team_member": self.member.pk,
                "grade": grade_1.pk,
                "from_date": date(2026, 4, 1),
                "to_date": date(2026, 4, 5),
            },
            instance=first_period,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["to_date"], date(2026, 4, 10))
