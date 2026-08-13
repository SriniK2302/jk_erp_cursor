from django.contrib.auth import get_user_model
from django.test import TestCase

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from sales.services.models import Service
from sales.udins.models import Udin
from sales.udins.service_remarks_build import (
    bulk_fill_client_from_remarks,
    build_certification_service_remarks,
    derive_service_remarks,
    find_client_by_code_in_remarks,
    service_remarks_is_blank,
    strip_remarks_client_code,
)


class ServiceRemarksBuildTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="sr_user", password="pass12345")
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="SRTest",
            defaults={"created_by": self.user},
        )
        self.client_row = Client.objects.create(
            client_name="Sri Vishnu Shankar Mills",
            client_short_name="Sri Vishnu Shankar",
            client_code="SVSM",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.cert = Service.objects.create(
            service_desc="Certification",
            service_code="CERT",
            created_by=self.user,
        )
        self.audit = Service.objects.create(
            service_desc="Statutory Audit",
            service_code="SAUD",
            created_by=self.user,
        )

    def test_strip_remarks_client_code(self):
        out = strip_remarks_client_code(
            remarks="SVSM Form 146 FILOPA 20260502",
            client=self.client_row,
        )
        self.assertEqual(out, "Form 146 FILOPA 20260502")

    def test_derive_service_remarks_full_line(self):
        out = derive_service_remarks(
            remarks="SVSM Form 146 FILOPA 20260502",
            client=self.client_row,
            service=self.cert,
        )
        self.assertEqual(
            out,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )

    def test_derive_infers_client_from_remarks_prefix(self):
        out = derive_service_remarks(
            remarks="SVSM Form 146 FILOPA 20260502",
            client=None,
            service=None,
        )
        self.assertEqual(
            out,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )

    def test_non_certification_returns_none(self):
        out = derive_service_remarks(
            remarks="SVSM Form 146 FILOPA 20260502",
            client=self.client_row,
            service=self.audit,
        )
        self.assertIsNone(out)

    def test_service_remarks_is_blank(self):
        self.assertTrue(service_remarks_is_blank(""))
        self.assertFalse(service_remarks_is_blank("Fee for issuing certificate for X."))

    def test_build_certification_service_remarks(self):
        self.assertEqual(
            build_certification_service_remarks(stripped_remarks="Form 146"),
            "Fee for issuing certificate for Form 146.",
        )

    def test_find_client_by_code_after_date_in_remarks(self):
        client = find_client_by_code_in_remarks(
            "20260511 SVSM CGP Certificate as on 17-08-2025"
        )
        self.assertEqual(client, self.client_row)

    def test_bulk_fill_client_from_remarks(self):
        udin = Udin.objects.create(
            udin="BCFR-001",
            remarks="20260511 SVSM CGP Certificate as on 17-08-2025",
            created_by=self.user,
        )
        updated, skipped = bulk_fill_client_from_remarks()
        udin.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertEqual(udin.client_id, self.client_row.pk)

    def test_find_client_by_short_code_prefix_in_remarks(self):
        ramco = Client.objects.create(
            client_name="Ramco Systems Limited",
            client_short_name="Ramco Systems",
            client_code="RSL1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.assertEqual(
            find_client_by_code_in_remarks("RSL ESOS Allotment Certificate"),
            ramco,
        )
        self.assertEqual(
            find_client_by_code_in_remarks("RASL SFS Statutory Audit Certificate"),
            None,
        )
        rasl = Client.objects.create(
            client_name="Ramco Systems Limited",
            client_short_name="Ramco RASL",
            client_code="RASL",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.assertEqual(
            find_client_by_code_in_remarks("RASL SFS Statutory Audit Certificate"),
            rasl,
        )
