from django.test import TestCase

from .forms import QualificationForm


class QualificationFormTests(TestCase):
    def test_qualification_code_is_trimmed_uppercased_and_limited(self):
        form = QualificationForm(
            data={
                "qualification_desc": "Chartered Accountant",
                "qualification_code": " ca1 ",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["qualification_code"], "CA1")

    def test_common_word_code_is_sanitized(self):
        form = QualificationForm(
            data={
                "qualification_desc": "Chartered Accountant",
                "qualification_code": "this",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["qualification_code"], "THIX")
