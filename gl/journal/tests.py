from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from config.models import ChartOfAccount
from gl.fiscal_years.models import FiscalYear

from .models import GlHeader, GlLine, TbTable, TbTableMonth
from .posting import GlAuthorisedVoucherLineSpec, GlAuthorisedVoucherPosting
from .tb_sync import apply_tb_delta_for_gl_header, rebuild_tb_table_from_gl_lines
from .trial_balance_report import build_gl_trial_balance_rows


class AuthorisedGlGuardsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="gl_guard_user", password="pass12345")
        self.coa_income = ChartOfAccount.objects.create(
            account_name="Professional Fees",
            account_code="5000",
            plbs=ChartOfAccount.PLBS_PL,
            plbs_type=ChartOfAccount.TYPE_INCOME,
            created_by=self.user,
        )
        self.coa_recv = ChartOfAccount.objects.create(
            account_name="Trade Receivables",
            account_code="1200",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=self.user,
        )

    def test_authorised_header_cannot_be_edited_or_deleted(self):
        hdr = GlHeader.objects.create(
            tran_date=date(2026, 4, 29),
            tran_id="SLS-0001",
            source=GlHeader.Source.SALES,
            narration="Test post",
            ym="M 2026 04",
            line_count=2,
            status=GlHeader.Status.AUTHORISED,
            created_by=self.user,
        )
        hdr.narration = "Changed"
        with self.assertRaises(ValidationError):
            hdr.save()
        with self.assertRaises(ValidationError):
            hdr.delete()

    def test_authorised_line_allows_only_value_period_edit(self):
        hdr = GlHeader.objects.create(
            tran_date=date(2026, 4, 29),
            tran_id="SLS-0002",
            source=GlHeader.Source.SALES,
            narration="Authorised",
            ym="M 2026 04",
            line_count=1,
            status=GlHeader.Status.FRESH,
            created_by=self.user,
        )
        ln = GlLine.objects.create(
            header=hdr,
            line_no=1,
            account=self.coa_recv,
            line_description="Receivable",
            amount=Decimal("100.00"),
            ym="M 2026 04",
            rm_or="M 2026 04",
            value_ym="M 2026 04",
        )
        GlHeader.objects.filter(pk=hdr.pk).update(status=GlHeader.Status.AUTHORISED)
        hdr.refresh_from_db()
        ln.refresh_from_db()
        ln.value_ym = "M 2026 05"
        ln.save()
        ln.refresh_from_db()
        self.assertEqual(ln.value_ym, "M 2026 05")

        ln.amount = Decimal("-100.00")
        with self.assertRaises(ValidationError):
            ln.save()

        with self.assertRaises(ValidationError):
            ln.delete()


class GlAuthorisedVoucherPostingTests(TestCase):
    """Shared GL voucher writer (Sales / Purchases / Payroll all build specs and call this)."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="voucher_post_user", password="pass12345")
        self.coa_recv = ChartOfAccount.objects.create(
            account_name="Recv",
            account_code="VP1200",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=self.user,
        )
        self.coa_fee = ChartOfAccount.objects.create(
            account_name="Income",
            account_code="VP5000",
            plbs=ChartOfAccount.PLBS_PL,
            plbs_type=ChartOfAccount.TYPE_INCOME,
            created_by=self.user,
        )

    def test_balanced_voucher_authorised_with_lines(self):
        ym = "M 2026 04"
        posting = GlAuthorisedVoucherPosting()
        hdr = posting.execute(
            tran_date=date(2026, 4, 10),
            tran_id="VP-0001",
            source=GlHeader.Source.PAYROLL,
            narration="Payroll accrual test",
            header_ym=ym,
            line_specs=[
                GlAuthorisedVoucherLineSpec(
                    account=self.coa_recv,
                    amount=Decimal("100.00"),
                    line_description="Dr",
                    ym=ym,
                    rm_or=ym,
                    value_ym=ym,
                ),
                GlAuthorisedVoucherLineSpec(
                    account=self.coa_fee,
                    amount=Decimal("-100.00"),
                    line_description="Cr",
                    ym=ym,
                    rm_or=ym,
                    value_ym=ym,
                ),
            ],
            created_by=self.user,
        )
        self.assertEqual(hdr.status, GlHeader.Status.AUTHORISED)
        self.assertEqual(hdr.source, GlHeader.Source.PAYROLL)
        self.assertEqual(hdr.lines.count(), 2)

    def test_unbalanced_voucher_rejected(self):
        posting = GlAuthorisedVoucherPosting()
        ym = "M 2026 04"
        with self.assertRaises(ValidationError):
            posting.execute(
                tran_date=date(2026, 4, 10),
                tran_id="VP-BAD",
                source=GlHeader.Source.JV,
                narration="",
                header_ym=ym,
                line_specs=[
                    GlAuthorisedVoucherLineSpec(
                        account=self.coa_recv,
                        amount=Decimal("100.00"),
                        line_description="",
                        ym=ym,
                    ),
                    GlAuthorisedVoucherLineSpec(
                        account=self.coa_fee,
                        amount=Decimal("-99.00"),
                        line_description="",
                        ym=ym,
                    ),
                ],
                created_by=self.user,
            )
        self.assertEqual(GlHeader.objects.filter(tran_id="VP-BAD").count(), 0)


class TbTableSyncTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tb_sync_user", password="pass12345")
        self.coa_recv = ChartOfAccount.objects.create(
            account_name="Trade Receivables",
            account_code="TB1200",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=self.user,
        )
        self.coa_fee = ChartOfAccount.objects.create(
            account_name="Professional Fees",
            account_code="TB5000",
            plbs=ChartOfAccount.PLBS_PL,
            plbs_type=ChartOfAccount.TYPE_INCOME,
            created_by=self.user,
        )
        self.fy = FiscalYear.objects.create(
            fy_no="FYTB",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.user,
        )

    def test_apply_tb_delta_for_authorised_header(self):
        hdr = GlHeader.objects.create(
            tran_date=date(2026, 5, 15),
            tran_id="TB-0001",
            source=GlHeader.Source.SALES,
            narration="",
            ym="M 2026 05",
            line_count=2,
            status=GlHeader.Status.FRESH,
            created_by=self.user,
        )
        GlLine.objects.create(
            header=hdr,
            line_no=1,
            account=self.coa_recv,
            line_description="Dr",
            amount=Decimal("118.00"),
            ym="M 2026 05",
            rm_or="M 2026 05",
            value_ym="M 2026 05",
        )
        GlLine.objects.create(
            header=hdr,
            line_no=2,
            account=self.coa_fee,
            line_description="Cr",
            amount=Decimal("-118.00"),
            ym="M 2026 05",
            rm_or="M 2026 05",
            value_ym="M 2026 05",
        )
        hdr.status = GlHeader.Status.AUTHORISED
        hdr.save(update_fields=["status"])
        apply_tb_delta_for_gl_header(hdr)
        self.assertEqual(TbTable.objects.filter(fiscal_year=self.fy).count(), 2)
        recv = TbTable.objects.get(fiscal_year=self.fy, account_code="TB1200")
        fee = TbTable.objects.get(fiscal_year=self.fy, account_code="TB5000")
        self.assertEqual(recv.amount, Decimal("118.00"))
        self.assertEqual(fee.amount, Decimal("-118.00"))
        self.assertEqual(TbTableMonth.objects.filter(fiscal_year=self.fy).count(), 2)
        mrecv = TbTableMonth.objects.get(
            fiscal_year=self.fy, account_code="TB1200"
        )
        self.assertEqual(mrecv.period_from, date(2026, 5, 1))
        self.assertEqual(mrecv.period_to, date(2026, 5, 31))
        self.assertEqual(mrecv.amount, Decimal("118.00"))

    def test_rebuild_tb_table_from_gl_lines(self):
        hdr = GlHeader.objects.create(
            tran_date=date(2026, 6, 1),
            tran_id="TB-0002",
            source=GlHeader.Source.SALES,
            narration="",
            ym="M 2026 06",
            line_count=1,
            status=GlHeader.Status.FRESH,
            created_by=self.user,
        )
        GlLine.objects.create(
            header=hdr,
            line_no=1,
            account=self.coa_recv,
            line_description="",
            amount=Decimal("50.00"),
            ym="M 2026 06",
            rm_or="M 2026 06",
            value_ym="M 2026 06",
        )
        GlHeader.objects.filter(pk=hdr.pk).update(status=GlHeader.Status.AUTHORISED)
        TbTable.objects.create(
            fiscal_year=self.fy, account_code="TB1200", amount=Decimal("999.00")
        )
        n = rebuild_tb_table_from_gl_lines()
        self.assertEqual(n, 1)
        row = TbTable.objects.get(fiscal_year=self.fy, account_code="TB1200")
        self.assertEqual(row.amount, Decimal("50.00"))


class GlTrialBalanceReportTests(TestCase):
    """Posting-date TB: period slice vs opening BS + Retained Earnings."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="gl_tb_rep_user", password="pass12345")
        self.fy26 = FiscalYear.objects.create(
            fy_no="GT26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            created_by=self.user,
        )
        self.fy27 = FiscalYear.objects.create(
            fy_no="GT27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            created_by=self.user,
        )
        self.fy28 = FiscalYear.objects.create(
            fy_no="GT28",
            start_date=date(2027, 4, 1),
            end_date=date(2028, 3, 31),
            created_by=self.user,
        )
        self.coa_recv = ChartOfAccount.objects.create(
            account_name="Receivables",
            account_code="TBX1200",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_ASSET,
            created_by=self.user,
        )
        self.coa_fee = ChartOfAccount.objects.create(
            account_name="Fees",
            account_code="TBX5000",
            plbs=ChartOfAccount.PLBS_PL,
            plbs_type=ChartOfAccount.TYPE_INCOME,
            created_by=self.user,
        )
        self.coa_tax = ChartOfAccount.objects.create(
            account_name="GST Out",
            account_code="TBX2200",
            plbs=ChartOfAccount.PLBS_BS,
            plbs_type=ChartOfAccount.TYPE_LIABILITY,
            created_by=self.user,
        )

    def _post_balanced_voucher(self, *, tran_date, dr_code, dr_amt, cr_specs: list[tuple]):
        """One Dr line (account object by code) and one or more Cr lines summing to dr_amt."""
        hdr = GlHeader.objects.create(
            tran_date=tran_date,
            tran_id=f"TBX-{tran_date.isoformat()}",
            source=GlHeader.Source.SALES,
            narration="",
            ym=f"M {tran_date.year} {tran_date.month:02d}",
            line_count=1,
            status=GlHeader.Status.FRESH,
            created_by=self.user,
        )
        recv = ChartOfAccount.objects.get(account_code=dr_code)
        line_no = 1
        GlLine.objects.create(
            header=hdr,
            line_no=line_no,
            account=recv,
            line_description="",
            amount=dr_amt,
            ym=hdr.ym,
            rm_or=hdr.ym,
            value_ym=hdr.ym,
        )
        line_no += 1
        for code, amt in cr_specs:
            acct = ChartOfAccount.objects.get(account_code=code)
            GlLine.objects.create(
                header=hdr,
                line_no=line_no,
                account=acct,
                line_description="",
                amount=-amt,
                ym=hdr.ym,
                rm_or=hdr.ym,
                value_ym=hdr.ym,
            )
            line_no += 1
        hdr.line_count = line_no - 1
        hdr.status = GlHeader.Status.AUTHORISED
        hdr.save(update_fields=["line_count", "status"])

    def test_period_mode_fy27_lists_each_account(self):
        # Posting inside FY27
        self._post_balanced_voucher(
            tran_date=date(2026, 8, 1),
            dr_code="TBX1200",
            dr_amt=Decimal("1180.00"),
            cr_specs=[("TBX5000", Decimal("1000.00")), ("TBX2200", Decimal("180.00"))],
        )
        rows, dr, cr = build_gl_trial_balance_rows(self.fy27)
        self.assertEqual(dr, cr)
        codes = {r["account_code"]: r for r in rows if r["account_code"]}
        self.assertIn("TBX1200", codes)
        self.assertIn("TBX5000", codes)
        self.assertIn("TBX2200", codes)
        self.assertEqual(codes["TBX1200"]["debit"], Decimal("1180.00"))
        self.assertEqual(codes["TBX5000"]["credit"], Decimal("1000.00"))

    def test_opening_mode_fy28_bs_and_retained_earnings(self):
        # All postings before FY28 window
        self._post_balanced_voucher(
            tran_date=date(2027, 1, 10),
            dr_code="TBX1200",
            dr_amt=Decimal("1180.00"),
            cr_specs=[("TBX5000", Decimal("1000.00")), ("TBX2200", Decimal("180.00"))],
        )
        rows, dr, cr = build_gl_trial_balance_rows(self.fy28)
        self.assertEqual(dr, cr)
        names = [r["account_name"] for r in rows]
        self.assertIn("Receivables", names)
        self.assertIn("GST Out", names)
        self.assertIn("Retained Earnings", names)
        re = next(r for r in rows if r["account_name"] == "Retained Earnings")
        self.assertEqual(re["account_code"], "")
        self.assertEqual(re["credit"], Decimal("1000.00"))
