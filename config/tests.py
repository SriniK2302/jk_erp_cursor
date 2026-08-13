import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from engagements.models import (
    DivisionWorkArea,
    Engagement,
    EngagementDivision,
    EngagementSchedule,
    EngagementTeamAssignment,
    EngagementWorkArea,
    EngagementWorkAreaPeriod,
)
from config.models import ChartOfAccount
from gl.fiscal_years.models import FiscalYear
from gl.journal.models import TbTableMonth
from hr.teams.models import TeamMember, team_members_linkable_to_user
from sales.services.models import Service
from sales.invoices.models import Invoice, InvoiceLine
from sales.udins.models import Udin

from .admin import AdminUserCreationForm
from admin.forms import UserAccountForm
from .models import UserTodo


class AuditAccountsDocumentRulesTests(SimpleTestCase):
    def test_extension_label_maps_formats(self):
        from utilities.audit_accounts_documents import extension_label

        self.assertEqual(extension_label(".xlsx"), "Excel")
        self.assertEqual(extension_label("xlsx"), "Excel")
        self.assertEqual(extension_label(".pdf"), "PDF")
        self.assertEqual(extension_label(".docx"), "Word")
        self.assertIsNone(extension_label(".msg"))


class AuditTriageMoveTests(SimpleTestCase):
    def test_move_rejects_paths_outside_scan_root(self):
        import tempfile
        from pathlib import Path

        from utilities.audit_document_triage import move_triage_matches

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "review"
            dest = Path(td) / "out"
            root.mkdir()
            dest.mkdir()
            inside = root / "inside.txt"
            inside.write_text("x", encoding="utf-8")
            outside = Path(td) / "outside.txt"
            outside.write_text("y", encoding="utf-8")
            r = move_triage_matches(
                scan_root=root,
                destination_base=dest,
                folder_slug="01_Audit_Appointment",
                source_paths=[str(inside), str(outside)],
            )
            self.assertEqual(r.moved_count, 1)
            self.assertEqual(len(r.skipped_paths), 1)
            self.assertTrue((dest / "01_Audit_Appointment" / "inside.txt").is_file())


class UserAccountFormTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin",
            password="pass12345",
            is_superuser=True,
        )
        self.u1 = get_user_model().objects.create_user(
            username="alice",
            password="pass12345",
            email="alice@example.com",
        )
        self.u2 = get_user_model().objects.create_user(
            username="bob",
            password="pass12345",
            email="bob@example.com",
        )
        self.tm_a = TeamMember.objects.create(
            first_name="Alice",
            last_name="Staff",
            called_as="Alice",
            code="AL01",
            created_by=self.admin,
        )
        self.tm_b = TeamMember.objects.create(
            first_name="Bob",
            last_name="Staff",
            called_as="Bob",
            code="BO01",
            created_by=self.admin,
        )

    def test_save_links_team_member_and_clears_previous(self):
        form = UserAccountForm(
            data={
                "email": "alice@corp.example",
                "first_name": "Alice",
                "last_name": "User",
                "is_active": True,
                "team_member": self.tm_a.pk,
            },
            instance=self.u1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.tm_a.refresh_from_db()
        self.assertEqual(self.tm_a.user_id, self.u1.pk)

        form2 = UserAccountForm(
            data={
                "email": "alice@corp.example",
                "first_name": "Alice",
                "last_name": "User",
                "is_active": True,
                "team_member": self.tm_b.pk,
            },
            instance=self.u1,
        )
        self.assertTrue(form2.is_valid(), form2.errors)
        form2.save()
        self.tm_a.refresh_from_db()
        self.tm_b.refresh_from_db()
        self.assertIsNone(self.tm_a.user_id)
        self.assertEqual(self.tm_b.user_id, self.u1.pk)

    def test_email_required(self):
        form = UserAccountForm(
            data={
                "email": "",
                "first_name": "A",
                "last_name": "L",
                "is_active": True,
                "team_member": "",
            },
            instance=self.u1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_save_updates_module_access_groups(self):
        form = UserAccountForm(
            data={
                "email": "alice@example.com",
                "first_name": "Alice",
                "last_name": "User",
                "is_active": True,
                "can_use_engagements": True,
                "can_use_setup": False,
                "can_use_tools": True,
                "team_member": "",
            },
            instance=self.u1,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(
            self.u1.groups.filter(name="module_engagements").exists()
        )
        self.assertTrue(self.u1.groups.filter(name="module_tools").exists())
        self.assertFalse(self.u1.groups.filter(name="module_setup").exists())
        self.assertTrue(Group.objects.filter(name="module_engagements").exists())


class TeamMembersLinkableQuerysetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="admin",
            password="pass12345",
            is_superuser=True,
        )
        self.linked_user = User.objects.create_user(
            username="linked",
            password="pass12345",
            email="linked@example.com",
        )
        self.tm_free = TeamMember.objects.create(
            first_name="Free",
            last_name="Agent",
            called_as="Free",
            code="FR01",
            created_by=self.admin,
        )
        self.tm_linked = TeamMember.objects.create(
            first_name="Taken",
            last_name="Agent",
            called_as="Taken",
            code="TA01",
            created_by=self.admin,
            user=self.linked_user,
        )

    def test_unmapped_only_when_no_user(self):
        qs = team_members_linkable_to_user(None)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.tm_free.pk, ids)
        self.assertNotIn(self.tm_linked.pk, ids)

    def test_add_user_admin_form_same_queryset(self):
        form = AdminUserCreationForm()
        ids = set(form.fields["team_member"].queryset.values_list("pk", flat=True))
        self.assertIn(self.tm_free.pk, ids)
        self.assertNotIn(self.tm_linked.pk, ids)

    def test_change_user_includes_current_link(self):
        qs = team_members_linkable_to_user(self.linked_user)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.tm_linked.pk, ids)
        self.assertIn(self.tm_free.pk, ids)


class SetupUsersViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_user(
            username="su",
            password="pass12345",
            is_superuser=True,
        )
        self.normal = User.objects.create_user(
            username="norm",
            password="pass12345",
            is_superuser=False,
        )

    def test_superuser_can_open_users_list(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("setup_users"))
        self.assertEqual(response.status_code, 200)

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.normal)
        response = self.client.get(reverse("setup_users"))
        self.assertEqual(response.status_code, 403)


class UserTodoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(
            username="alice_todo",
            password="pass12345",
        )
        self.bob = User.objects.create_user(
            username="bob_todo",
            password="pass12345",
        )
        self.todo = UserTodo.objects.create(
            user=self.alice,
            title="Review ledger",
            description="Q1 files",
            target_date=None,
        )

    def test_user_cannot_edit_other_users_todo(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("my_todo_edit", args=[self.todo.pk]))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_list_and_toggle(self):
        self.client.force_login(self.alice)
        r = self.client.get(reverse("my_todos"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Review ledger")
        self.assertFalse(UserTodo.objects.get(pk=self.todo.pk).is_completed)
        r2 = self.client.post(reverse("my_todo_toggle", args=[self.todo.pk]))
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(UserTodo.objects.get(pk=self.todo.pk).is_completed)


class HomeScheduledWorkListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="home_wl_user",
            password="pass12345",
        )
        self.user.groups.add(Group.objects.get_or_create(name="module_engagements")[0])
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Work List Corp",
            client_short_name="WLC",
            client_code="WLC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY77",
            start_date=date(2076, 4, 1),
            end_date=date(2077, 3, 31),
            created_by=self.user,
        )
        self.service = Service.objects.create(
            service_desc="WL Audit",
            service_code="WLAD",
            created_by=self.user,
        )
        self.engagement = Engagement.objects.create(
            client=self.client_item,
            fiscal_year=self.fy,
            service=self.service,
            created_by=self.user,
        )
        self.member = TeamMember.objects.create(
            first_name="Home",
            last_name="User",
            called_as="Home",
            code="HM01",
            user=self.user,
            created_by=self.user,
        )
        EngagementTeamAssignment.objects.create(
            engagement=self.engagement,
            team_member=self.member,
            planned_start=date(2076, 5, 1),
            planned_finish=date(2076, 5, 20),
            created_by=self.user,
        )

    def test_home_lists_scheduled_engagements(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2076, 5, 1),
            planned_finish=date(2076, 5, 20),
            created_by=self.user,
        )
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "Scheduled")

        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Work list")
        self.assertContains(response, self.client_item.display_name)
        self.assertContains(response, "2076-05-20")
        self.assertContains(
            response,
            reverse("engagement_documentation_maps", kwargs={"engagement_pk": self.engagement.pk}),
        )
        self.assertContains(
            response,
            reverse("timer_start_engagement", args=[self.engagement.pk]),
        )
        self.assertContains(
            response,
            reverse("engagement_work_areas", kwargs={"engagement_pk": self.engagement.pk}),
        )
        self.assertContains(response, "Engagement (no work areas yet)")

    def test_home_work_list_shows_open_work_area_schedule_row(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2076, 5, 1),
            planned_finish=date(2076, 5, 20),
            created_by=self.user,
        )
        self.engagement.refresh_from_db()
        ewa = EngagementWorkArea.objects.create(
            engagement=self.engagement,
            work_area_name="Tax audit phase",
            created_by=self.user,
        )
        EngagementWorkAreaPeriod.objects.create(
            work_area=ewa,
            planned_start=date(2076, 5, 10),
            planned_finish=date(2076, 5, 18),
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tax audit phase")
        self.assertContains(response, "2076-05-18")
        self.assertNotContains(response, "Engagement (no work areas yet)")
        self.assertContains(
            response,
            reverse(
                "timer_start_engagement_work_area",
                args=[self.engagement.pk, ewa.pk],
            ),
        )

    def test_home_work_list_shows_division_work_area_without_schedule_period(self):
        EngagementSchedule.objects.create(
            engagement=self.engagement,
            planned_start=date(2076, 5, 1),
            planned_finish=date(2076, 5, 20),
            created_by=self.user,
        )
        self.engagement.refresh_from_db()
        div = EngagementDivision.objects.create(
            engagement=self.engagement,
            division_name="Integrated system",
            created_by=self.user,
        )
        dwa = DivisionWorkArea.objects.create(
            division=div,
            work_area_name="Timesheet system",
            sort_order=1,
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Integrated system · Timesheet system")
        self.assertNotContains(response, "Engagement (no work areas yet)")
        self.assertContains(
            response,
            reverse(
                "timer_start_division_work_area",
                args=[div.pk, dwa.pk],
            ),
        )

    def test_home_work_list_empty_when_none_scheduled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No open work items right now.")


class InvoiceViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.super = User.objects.create_user(
            username="inv_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.no_setup = User.objects.create_user(
            username="inv_plain",
            password="pass12345",
        )

    def test_invoices_list_forbidden_without_setup_module(self):
        self.client.force_login(self.no_setup)
        response = self.client.get(reverse("invoices"))
        self.assertEqual(response.status_code, 403)

    def test_invoices_list_ok_for_superuser(self):
        self.client.force_login(self.super)
        response = self.client.get(reverse("invoices"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoices")

    def test_home_shows_manage_invoices_tile_for_setup_group(self):
        g, _ = Group.objects.get_or_create(name="module_setup")
        u = get_user_model().objects.create_user(
            username="setup_invoice_user",
            password="pass12345",
        )
        u.groups.add(g)
        self.client.force_login(u)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Invoices")
        self.assertContains(response, reverse("invoices"))
        self.assertContains(response, "GL")
        self.assertContains(response, reverse("gl_hub"))

    def test_gl_hub_forbidden_without_setup_module(self):
        u = get_user_model().objects.create_user(
            username="no_setup_gl",
            password="pass12345",
        )
        self.client.force_login(u)
        response = self.client.get(reverse("gl_hub"))
        self.assertEqual(response.status_code, 403)

    def test_gl_hub_ok_for_setup_group(self):
        g, _ = Group.objects.get_or_create(name="module_setup")
        u = get_user_model().objects.create_user(
            username="setup_gl_user",
            password="pass12345",
        )
        u.groups.add(g)
        self.client.force_login(u)
        response = self.client.get(reverse("gl_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chart of Accounts")
        self.assertContains(response, reverse("gl_trial_balance"))

    def test_gl_trial_balance_ok_for_setup_group(self):
        g, _ = Group.objects.get_or_create(name="module_setup")
        u = get_user_model().objects.create_user(
            username="setup_gl_tb_user",
            password="pass12345",
        )
        u.groups.add(g)
        self.client.force_login(u)
        response = self.client.get(reverse("gl_trial_balance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GL Trial Balance")

    def test_gl_trial_balance_forbidden_without_setup(self):
        u = get_user_model().objects.create_user(
            username="no_setup_gl_tb",
            password="pass12345",
        )
        self.client.force_login(u)
        response = self.client.get(reverse("gl_trial_balance"))
        self.assertEqual(response.status_code, 403)

    def test_gl_trial_balance_month_reads_tb_table_month(self):
        User = get_user_model()
        g, _ = Group.objects.get_or_create(name="module_setup")
        u = User.objects.create_user(username="gl_tb_month_view", password="pass12345")
        u.groups.add(g)
        coa = ChartOfAccount.objects.create(
            account_name="Cash Month TB",
            account_code="GMTB",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=u,
        )
        fy = FiscalYear.objects.create(
            fy_no="GT9",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=u,
        )
        TbTableMonth.objects.create(
            fiscal_year=fy,
            period_from=date(2026, 5, 1),
            period_to=date(2026, 5, 31),
            account_code=coa.account_code,
            amount=Decimal("50.00"),
        )
        self.client.force_login(u)
        url = f"{reverse('gl_trial_balance')}?fy={fy.pk}&month=2026-05-01"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tb_table_month")
        self.assertContains(response, "Cash Month TB")
        self.assertContains(response, "50.00")
        self.assertContains(response, "YTD through")

    def test_gl_trial_balance_month_ytd_sums_through_selected_month(self):
        User = get_user_model()
        g, _ = Group.objects.get_or_create(name="module_setup")
        u = User.objects.create_user(username="gl_tb_ytd_view", password="pass12345")
        u.groups.add(g)
        coa = ChartOfAccount.objects.create(
            account_name="YTD TB Cash",
            account_code="GYTB",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=u,
        )
        fy = FiscalYear.objects.create(
            fy_no="GTY",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=u,
        )
        TbTableMonth.objects.create(
            fiscal_year=fy,
            period_from=date(2026, 4, 1),
            period_to=date(2026, 4, 30),
            account_code=coa.account_code,
            amount=Decimal("100.00"),
        )
        TbTableMonth.objects.create(
            fiscal_year=fy,
            period_from=date(2026, 5, 1),
            period_to=date(2026, 5, 31),
            account_code=coa.account_code,
            amount=Decimal("50.00"),
        )
        self.client.force_login(u)
        base = f"{reverse('gl_trial_balance')}?fy={fy.pk}&month=2026-05-01"
        r_ytd = self.client.get(base)
        self.assertEqual(r_ytd.status_code, 200)
        self.assertContains(r_ytd, "YTD through")
        self.assertContains(r_ytd, "150.00")
        r_mo = self.client.get(f"{base}&ytd=0")
        self.assertEqual(r_mo.status_code, 200)
        self.assertContains(r_mo, "month only")
        self.assertContains(r_mo, "50.00")
        self.assertNotContains(r_mo, "150.00")

    def test_audit_document_renaming_filing_ok_for_tools_group(self):
        g, _ = Group.objects.get_or_create(name="module_tools")
        u = get_user_model().objects.create_user(
            username="tools_audit_doc_user", password="pass12345"
        )
        u.groups.add(g)
        self.client.force_login(u)
        response = self.client.get(reverse("audit_document_renaming_filing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit Document Renaming and Filing")
        self.assertContains(response, "Naming rules")
        self.assertContains(response, ".xlsx")
        self.assertContains(response, "audit_accounts_documents.py")

    def test_audit_document_triage_ok_for_tools_group(self):
        g, _ = Group.objects.get_or_create(name="module_tools")
        u = get_user_model().objects.create_user(
            username="tools_triage_user", password="pass12345"
        )
        u.groups.add(g)
        self.client.force_login(u)
        response = self.client.get(reverse("audit_document_triage"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Management representation")

    def test_audit_document_renaming_filing_forbidden_without_tools(self):
        u = get_user_model().objects.create_user(
            username="no_tools_audit_doc", password="pass12345"
        )
        self.client.force_login(u)
        response = self.client.get(reverse("audit_document_renaming_filing"))
        self.assertEqual(response.status_code, 403)


def _invoice_create_post_body(udin_pk, *, fy_pk, invoice_no, invoice_date, amount, narration="", desc="Fee for line"):
    """POST body for invoice create with maps formset (prefix ``maps``)."""
    return {
        "narration": narration,
        "invoice_date": invoice_date,
        "invoice_no": invoice_no,
        "fiscal_year": fy_pk,
        "status": "fresh",
        "maps-TOTAL_FORMS": "1",
        "maps-INITIAL_FORMS": "0",
        "maps-MIN_NUM_FORMS": "0",
        "maps-MAX_NUM_FORMS": "1000",
        "maps-0-udin": str(udin_pk),
        "maps-0-service_desc": desc,
        "maps-0-line_amount": str(amount),
        "maps-0-id": "",
        "maps-0-DELETE": "",
    }


class InvoiceUdinInvoicedFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="udin_flow_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="InvoiceUdinFlow",
            defaults={"created_by": self.admin},
        )
        self.cli = Client.objects.create(
            client_name="Udin Flow Corp",
            client_short_name="UFC",
            client_code="UFC1",
            classification=self.classification,
            is_active=True,
            created_by=self.admin,
        )
        self.svc = Service.objects.create(
            service_desc="Flow Svc",
            service_code="FLW1",
            created_by=self.admin,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY99",
            start_date=date(2098, 4, 1),
            end_date=date(2099, 3, 31),
            created_by=self.admin,
        )
        self.udin_pending = Udin.objects.create(
            udin="INV-FLOW-PENDING-001",
            client=self.cli,
            service=self.svc,
            inv_tv_amount=Decimal("250.00"),
            is_invoiced=False,
            created_by=self.admin,
        )
        self.udin_invoiced = Udin.objects.create(
            udin="INV-FLOW-ALREADY-DONE-002",
            client=self.cli,
            service=self.svc,
            inv_tv_amount=Decimal("100.00"),
            is_invoiced=True,
            created_by=self.admin,
        )

    def test_create_invoice_marks_udin_invoiced(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                self.udin_pending.pk,
                fy_pk=self.fy.pk,
                invoice_no="INV-FLOW-01",
                invoice_date="2098-06-01",
                amount="250.00",
                desc="Fee for Flow Svc",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.udin_pending.refresh_from_db()
        self.assertTrue(self.udin_pending.is_invoiced)
        inv = Invoice.objects.get(invoice_no="INV-FLOW-01")
        self.assertEqual(inv.taxes, Decimal("45.00"))
        self.assertEqual(inv.inv_gross, Decimal("295.00"))
        lines = list(inv.invoice_lines.order_by("line_no").values_list("line_type", flat=True))
        self.assertEqual(lines, ["Service", "CGST", "SGST"])

    def test_create_invoice_igst_client_has_two_lines(self):
        ud_igst = Udin.objects.create(
            udin="INV-FLOW-IGST-UDIN",
            client=self.cli,
            service=self.svc,
            inv_tv_amount=Decimal("100.00"),
            is_invoiced=False,
            created_by=self.admin,
        )
        self.cli.invoice_tax_type = Client.INVOICE_TAX_IGST
        self.cli.save(update_fields=["invoice_tax_type"])
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                ud_igst.pk,
                fy_pk=self.fy.pk,
                invoice_no="INV-FLOW-IGST",
                invoice_date="2098-06-02",
                amount="100.00",
            ),
        )
        self.assertEqual(response.status_code, 302)
        inv = Invoice.objects.get(invoice_no="INV-FLOW-IGST")
        types = list(inv.invoice_lines.order_by("line_no").values_list("line_type", flat=True))
        self.assertEqual(types, ["Service", "IGST"])
        self.assertEqual(inv.taxes, Decimal("18.00"))
        self.assertEqual(inv.inv_gross, Decimal("118.00"))

    def test_delete_invoice_clears_udin_invoiced(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                self.udin_pending.pk,
                fy_pk=self.fy.pk,
                invoice_no="INV-FLOW-DEL",
                invoice_date="2098-06-01",
                amount="250.00",
            ),
        )
        inv = Invoice.objects.get(invoice_no="INV-FLOW-DEL")
        self.udin_pending.refresh_from_db()
        self.assertTrue(self.udin_pending.is_invoiced)
        self.client.post(
            reverse("invoices"),
            {"action": "delete", "pk": inv.pk},
        )
        self.udin_pending.refresh_from_db()
        self.assertFalse(self.udin_pending.is_invoiced)

    def test_add_invoice_form_lists_only_pending_udins(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("invoice_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.udin_pending.udin)
        self.assertNotContains(response, self.udin_invoiced.udin)


class InvoiceNextNoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="inv_next_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.plain = User.objects.create_user(
            username="inv_next_plain",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="InvoiceNextNo",
            defaults={"created_by": self.admin},
        )
        self.cli = Client.objects.create(
            client_name="Next No Corp",
            client_short_name="NNC",
            client_code="NNC1",
            classification=self.classification,
            is_active=True,
            created_by=self.admin,
        )
        self.svc = Service.objects.create(
            service_desc="NN Svc",
            service_code="NN01",
            created_by=self.admin,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.admin,
        )

    def test_next_invoice_no_helper_first_and_second(self):
        from sales.invoices.invoice_numbers import next_invoice_no

        d = date(2026, 4, 29)
        self.assertEqual(
            next_invoice_no(client=self.cli, invoice_date=d),
            "FY27-NNC1-001",
        )
        Invoice.objects.create(
            client=self.cli,
            service=self.svc,
            fiscal_year=self.fy,
            invoice_date=d,
            invoice_no="FY27-NNC1-001",
            inv_taxable_value=Decimal("10.00"),
            taxes=Decimal("0"),
            inv_gross=Decimal("10.00"),
            created_by=self.admin,
        )
        self.assertEqual(
            next_invoice_no(client=self.cli, invoice_date=d),
            "FY27-NNC1-002",
        )

    def test_next_invoice_no_endpoint_for_superuser(self):
        self.client.force_login(self.admin)
        url = (
            reverse("invoice_next_no")
            + f"?client_id={self.cli.pk}&invoice_date=2026-04-29"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["invoice_no"], "FY27-NNC1-001")

    def test_next_invoice_no_forbidden_without_setup(self):
        self.client.force_login(self.plain)
        url = (
            reverse("invoice_next_no")
            + f"?client_id={self.cli.pk}&invoice_date=2026-04-29"
        )
        self.assertEqual(self.client.get(url).status_code, 403)


class InvoicePreviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="inv_preview_admin",
            password="pass12345",
            is_superuser=True,
        )
        self.plain = User.objects.create_user(
            username="inv_preview_plain",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="InvoicePreview",
            defaults={"created_by": self.admin},
        )
        self.cli = Client.objects.create(
            client_name="Preview Corp",
            client_short_name="PRC",
            client_code="PRC1",
            classification=self.classification,
            is_active=True,
            created_by=self.admin,
        )
        self.svc = Service.objects.create(
            service_desc="Preview Svc",
            service_code="PRV1",
            created_by=self.admin,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FY88",
            start_date=date(2090, 4, 1),
            end_date=date(2091, 3, 31),
            created_by=self.admin,
        )
        self.udin = Udin.objects.create(
            udin="PREVIEW-UDIN-001",
            client=self.cli,
            service=self.svc,
            inv_tv_amount=Decimal("3300.00"),
            is_invoiced=False,
            created_by=self.admin,
        )

    def test_invoice_preview_ok_for_superuser(self):
        self.client.force_login(self.admin)
        nar = "PREVIEW STORED NARRATION UNIQUE987"
        self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                self.udin.pk,
                fy_pk=self.fy.pk,
                invoice_no="PREVIEW-INV-001",
                invoice_date="2090-06-01",
                amount="3300.00",
                narration=nar,
                desc="Fee for Preview Svc",
            ),
        )
        inv = Invoice.objects.get(invoice_no="PREVIEW-INV-001")
        response = self.client.get(reverse("invoice_preview", args=[inv.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INVOICE")
        self.assertContains(response, "PREVIEW-INV-001")
        self.assertContains(response, "3,300")
        self.assertContains(response, nar)
        self.assertContains(response, "Rupees")
        self.assertContains(response, "Chartered Accountants")

    def test_invoice_preview_narration_statutory_fallback_when_blank(self):
        from sales.invoices.narration_build import reload_narration_templates

        reload_narration_templates()
        svc = Service.objects.create(
            service_desc="statutory audit",
            service_code="SAPV",
            created_by=self.admin,
        )
        ud = Udin.objects.create(
            udin="PREVIEW-UDIN-SAUD",
            client=self.cli,
            service=svc,
            ay_fy="FY88",
            inv_tv_amount=Decimal("500.00"),
            is_invoiced=False,
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                ud.pk,
                fy_pk=self.fy.pk,
                invoice_no="PREVIEW-INV-FALLBACK",
                invoice_date="2090-06-20",
                amount="500.00",
                desc="Fee for statutory audit",
            ),
        )
        inv = Invoice.objects.get(invoice_no="PREVIEW-INV-FALLBACK")
        # Header narration is auto-filled from UDIN templates when left blank on save.
        self.assertIn("Statutory Audit", (inv.narration or ""))
        response = self.client.get(reverse("invoice_preview", args=[inv.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Statutory Audit")

    def test_invoice_preview_forbidden_without_setup(self):
        ud2 = Udin.objects.create(
            udin="PREVIEW-UDIN-002",
            client=self.cli,
            service=self.svc,
            inv_tv_amount=Decimal("100.00"),
            is_invoiced=False,
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse("invoice_create"),
            _invoice_create_post_body(
                ud2.pk,
                fy_pk=self.fy.pk,
                invoice_no="PREVIEW-INV-002",
                invoice_date="2090-06-02",
                amount="100.00",
            ),
        )
        inv = Invoice.objects.get(invoice_no="PREVIEW-INV-002")
        self.client.logout()
        self.client.force_login(self.plain)
        self.assertEqual(
            self.client.get(reverse("invoice_preview", args=[inv.pk])).status_code,
            403,
        )


class MoveFilesToFyFolderTests(TestCase):
    """FY folder move: ``YYYY MM DD`` / ``YYYY MM`` prefix → ``FYxx`` (April–March)."""

    def test_fy_folder_name_april_march_rule(self):
        from gl.fiscal_years.fy_calendar import fy_no_from_calendar_date

        self.assertEqual(fy_no_from_calendar_date(date(2025, 4, 1)), "FY26")
        self.assertEqual(fy_no_from_calendar_date(date(2025, 4, 28)), "FY26")
        self.assertEqual(fy_no_from_calendar_date(date(2025, 3, 31)), "FY25")
        self.assertEqual(fy_no_from_calendar_date(date(2024, 3, 15)), "FY24")

    def test_parse_date_prefix_ymd_then_ym(self):
        from utilities.move_files_to_fy_folder import _parse_date_from_file_prefix

        self.assertEqual(_parse_date_from_file_prefix("2025 04 28 rest.pdf"), date(2025, 4, 28))
        self.assertEqual(_parse_date_from_file_prefix("2025 04 rest.pdf"), date(2025, 4, 1))
        self.assertEqual(_parse_date_from_file_prefix("2025 03 x"), date(2025, 3, 1))
        self.assertIsNone(_parse_date_from_file_prefix("2025 13 01 x"))
        self.assertIsNone(_parse_date_from_file_prefix("short"))

    def test_moves_files_into_fy_subfolders(self):
        from utilities.move_files_to_fy_folder import move_direct_files_to_fy_folders

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2025 04 28 invoice.txt").write_text("a", encoding="utf-8")
            (root / "2025 04 summary.txt").write_text("b", encoding="utf-8")
            (root / "2025 03 note.txt").write_text("c", encoding="utf-8")
            (root / "no_prefix.txt").write_text("d", encoding="utf-8")

            report = move_direct_files_to_fy_folders(root)

            self.assertEqual(report.scanned_count, 4)
            self.assertEqual(report.moved_count, 3)
            self.assertEqual(report.skipped_count, 1)
            self.assertTrue((root / "FY26" / "2025 04 28 invoice.txt").is_file())
            self.assertTrue((root / "FY26" / "2025 04 summary.txt").is_file())
            self.assertTrue((root / "FY25" / "2025 03 note.txt").is_file())
            self.assertTrue((root / "no_prefix.txt").is_file())
