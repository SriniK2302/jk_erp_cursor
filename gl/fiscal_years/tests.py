from datetime import date

from django.test import TestCase

from .forms import FiscalYearForm, derive_fy_dates
from .fy_calendar import fy_no_from_calendar_date


class FiscalYearFormTests(TestCase):
    def test_fy_code_autopopulates_dates(self):
        form = FiscalYearForm(
            data={
                "fy_no": "fy25",
                "start_date": "",
                "end_date": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fy_no"], "FY25")
        self.assertEqual(form.cleaned_data["start_date"], date(2024, 4, 1))
        self.assertEqual(form.cleaned_data["end_date"], date(2025, 3, 31))

    def test_invalid_fy_code_is_rejected(self):
        form = FiscalYearForm(
            data={
                "fy_no": "2025",
                "start_date": "",
                "end_date": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("fy_no", form.errors)


class FyCalendarRuleTests(TestCase):
    """``fy_no_from_calendar_date`` matches ``derive_fy_dates`` FY windows."""

    def test_label_matches_derive_fy_dates_window(self):
        for d in (
            date(2024, 4, 1),
            date(2025, 1, 15),
            date(2025, 3, 31),
        ):
            label = fy_no_from_calendar_date(d)
            start, end = derive_fy_dates(label)
            self.assertEqual(start, date(2024, 4, 1))
            self.assertEqual(end, date(2025, 3, 31))
            self.assertLessEqual(start, d)
            self.assertLessEqual(d, end)

    def test_march_vs_april_boundary(self):
        self.assertEqual(fy_no_from_calendar_date(date(2025, 3, 31)), "FY25")
        self.assertEqual(fy_no_from_calendar_date(date(2025, 4, 1)), "FY26")
