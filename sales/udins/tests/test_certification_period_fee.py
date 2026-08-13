from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from sales.services.models import Service
from sales.udins.certification_period_fee import (
    bulk_apply_certification_period_fees_to_udins,
    certification_period_fee_for_udin,
    certification_period_fee_lookup,
    maybe_apply_certification_period_fee,
)
from sales.udins.models import CertificationPeriodFee, Udin


class CertificationPeriodFeeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cert_period_fee", password="pass12345")
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="CertPeriod",
            defaults={"created_by": self.user},
        )
        self.client_a = Client.objects.create(
            client_name="Ramco Systems",
            client_short_name="Ramco",
            client_code="RAM1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.client_b = Client.objects.create(
            client_name="Other Co",
            client_short_name="Other",
            client_code="OTH1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )
        self.cert = Service.objects.create(
            service_desc="Certification",
            service_code="CPCE",
            created_by=self.user,
        )
        CertificationPeriodFee.objects.create(
            client=self.client_a,
            from_date=date(2026, 4, 1),
            to_date=date(2027, 3, 31),
            fee_amount=Decimal("7500.00"),
        )
        CertificationPeriodFee.objects.create(
            client=self.client_b,
            from_date=date(2026, 4, 1),
            to_date=date(2027, 3, 31),
            fee_amount=Decimal("3300.00"),
        )

    def test_lookup_varies_by_client(self):
        signing = date(2026, 5, 2)
        self.assertEqual(
            certification_period_fee_lookup(client_id=self.client_a.pk, signing_date=signing),
            Decimal("7500.00"),
        )
        self.assertEqual(
            certification_period_fee_lookup(client_id=self.client_b.pk, signing_date=signing),
            Decimal("3300.00"),
        )

    def test_udin_gets_client_fee(self):
        udin = Udin.objects.create(
            udin="CPF-001",
            client=self.client_a,
            service=self.cert,
            date_of_signing_of_document="02-05-2026",
            created_by=self.user,
        )
        self.assertTrue(maybe_apply_certification_period_fee(udin, save=True))
        udin.refresh_from_db()
        self.assertEqual(udin.inv_tv_amount, Decimal("7500.00"))

    def test_wrong_client_no_fee(self):
        udin = Udin.objects.create(
            udin="CPF-002",
            client=self.client_b,
            service=self.cert,
            date_of_signing_of_document="02-05-2026",
            created_by=self.user,
        )
        self.assertEqual(certification_period_fee_for_udin(udin), Decimal("3300.00"))
        self.assertNotEqual(certification_period_fee_for_udin(udin), Decimal("7500.00"))

    def test_does_not_overwrite_existing_inv_tv(self):
        udin = Udin.objects.create(
            udin="CPF-003",
            client=self.client_a,
            service=self.cert,
            date_of_signing_of_document="02-05-2026",
            inv_tv_amount=Decimal("100.00"),
            created_by=self.user,
        )
        self.assertFalse(maybe_apply_certification_period_fee(udin, save=True))
