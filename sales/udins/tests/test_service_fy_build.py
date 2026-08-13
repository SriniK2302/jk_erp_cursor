from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from sales.services.models import Service
from sales.udins.service_fy_build import (
    derive_service_fy,
    normalize_service_fy,
    parse_udin_document_date,
)


class ServiceFyBuildTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="sfy_user", password="pass12345")
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="SFYTest",
            defaults={"created_by": self.user},
        )
        self.client_row = Client.objects.create(
            client_name="Test Co",
            client_short_name="Test",
            client_code="TST1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.cert = Service.objects.create(
            service_desc="Certification",
            service_code="CERT",
            created_by=self.user,
        )
        self.stat_audit = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="SAUD",
            created_by=self.user,
        )

    def test_normalize_service_fy(self):
        self.assertEqual(normalize_service_fy("fy26"), "FY26")
        self.assertEqual(normalize_service_fy("FY26 extra"), "FY26")
        self.assertIsNone(normalize_service_fy("2026"))
        self.assertIsNone(normalize_service_fy(""))

    def test_certification_from_document_date(self):
        out = derive_service_fy(
            service=self.cert,
            date_of_signing_of_document="02-05-2026",
        )
        self.assertEqual(out, "FY27")

    def test_certification_uses_document_date_only(self):
        out = derive_service_fy(
            service=self.cert,
            date_of_signing_of_document="02-05-2026",
            ay_fy="FY99",
            remarks="FY99",
        )
        self.assertEqual(out, "FY27")

    def test_document_date_when_service_not_set(self):
        out = derive_service_fy(
            service=None,
            date_of_signing_of_document="02-05-2026",
        )
        self.assertEqual(out, "FY27")

    def test_certification_april_boundary(self):
        out = derive_service_fy(
            service=self.cert,
            date_of_signing_of_document="01-04-2026",
        )
        self.assertEqual(out, "FY27")

    def test_audit_from_year_end_in_remarks(self):
        out = derive_service_fy(
            service=self.stat_audit,
            remarks="Statutory Audit YE 31.3.2026",
        )
        self.assertEqual(out, "FY26")

    def test_audit_from_fy_token_in_remarks(self):
        out = derive_service_fy(
            service=self.stat_audit,
            remarks="Kavin Stat Audit FY26",
        )
        self.assertEqual(out, "FY26")

    def test_audit_from_existing_ay_fy(self):
        out = derive_service_fy(
            service=self.stat_audit,
            ay_fy="fy27",
        )
        self.assertEqual(out, "FY27")

    def test_parse_udin_document_date(self):
        self.assertEqual(parse_udin_document_date("31-03-2026"), date(2026, 3, 31))
