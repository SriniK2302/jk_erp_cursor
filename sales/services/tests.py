from django.test import TestCase

from .forms import ServiceForm


class ServiceFormTests(TestCase):
    def test_service_code_is_trimmed_uppercased_and_limited(self):
        form = ServiceForm(
            data={
                "service_desc": "Payroll Processing",
                "service_code": " abcd ",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["service_code"], "ABCD")

    def test_common_word_code_is_sanitized(self):
        form = ServiceForm(
            data={
                "service_desc": "Statutory Audit",
                "service_code": "this",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["service_code"], "THIX")
