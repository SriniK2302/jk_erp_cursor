from django.test import TestCase

from .forms import GradeForm


class GradeFormTests(TestCase):
    def test_grade_code_is_trimmed_uppercased_and_limited(self):
        form = GradeForm(
            data={
                "grade_desc": "Senior Consultant",
                "grade_code": " scn5 ",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["grade_code"], "SCN5")

    def test_common_word_code_is_sanitized(self):
        form = GradeForm(
            data={
                "grade_desc": "Senior Consultant",
                "grade_code": "this",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["grade_code"], "THIX")
