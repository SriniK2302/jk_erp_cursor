from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client
from sales.services.models import Service
from sales.udins.models import Udin


class UdinBillingPrepViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="udin_prep_user", password="pass12345")
        self.client.force_login(self.user)
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="UdinPrep",
            defaults={"created_by": self.user},
        )
        self.client_row = Client.objects.create(
            client_name="Sri Vishnu Shankar Mills",
            client_short_name="SVSM",
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
        self.udin = Udin.objects.create(
            udin="26021510VUXBCA5922",
            remarks="SVSM Form 146 FILOPA 20260502",
            date_of_signing_of_document="02-05-2026",
            ay_fy="2026-2027",
            created_by=self.user,
        )

    def test_update_service_fy_preserves_client_and_service_from_post(self):
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "date_of_signing_of_document": "02-05-2026",
                "client": str(self.client_row.pk),
                "service": str(self.cert.pk),
                "ay_fy": "2026-2027",
                "derive_service_fy": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.udin.refresh_from_db()
        self.assertEqual(self.udin.ay_fy, "FY27")
        self.assertEqual(self.udin.client_id, self.client_row.pk)
        self.assertEqual(self.udin.service_id, self.cert.pk)

    def test_update_service_remarks_infers_client_from_remarks(self):
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "date_of_signing_of_document": "02-05-2026",
                "derive_service_remarks": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.udin.refresh_from_db()
        self.assertEqual(
            self.udin.service_remarks,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )

    def test_update_service_remarks_strips_client_code(self):
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "date_of_signing_of_document": "02-05-2026",
                "client": str(self.client_row.pk),
                "service": str(self.cert.pk),
                "derive_service_remarks": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.udin.refresh_from_db()
        self.assertEqual(
            self.udin.service_remarks,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )

    def test_update_service_remarks_replaces_when_user_blanks_field(self):
        self.udin.service_remarks = "Svsm Form 146 Filopa 20260502"
        self.udin.client = self.client_row
        self.udin.service = self.cert
        self.udin.save()
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "service_remarks": "",
                "date_of_signing_of_document": "02-05-2026",
                "client": str(self.client_row.pk),
                "service": str(self.cert.pk),
                "derive_service_remarks": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.udin.refresh_from_db()
        self.assertEqual(
            self.udin.service_remarks,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )
        self.assertContains(response, "Fee for issuing certificate for Form 146 FILOPA 20260502.")

    def test_update_service_remarks_shows_db_value_on_fy_update_without_overwrite(self):
        """Update Service FY must not block derive later; restore display only on FY path."""
        saved = "Fee for issuing certificate for Form 146 FILOPA 20260502."
        self.udin.service_remarks = saved
        self.udin.save()
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "service_remarks": "",
                "date_of_signing_of_document": "02-05-2026",
                "derive_service_fy": "1",
            },
        )
        self.assertIn(response.status_code, (200, 302))
        self.udin.refresh_from_db()
        self.assertEqual(self.udin.service_remarks, saved)

    def test_update_service_remarks_skips_when_already_set(self):
        self.udin.service_remarks = "Custom remarks kept"
        self.udin.save()
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "service_remarks": "Custom remarks kept",
                "date_of_signing_of_document": "02-05-2026",
                "client": str(self.client_row.pk),
                "service": str(self.cert.pk),
                "derive_service_remarks": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.udin.refresh_from_db()
        self.assertEqual(self.udin.service_remarks, "Custom remarks kept")

    def test_update_service_fy_preserves_service_remarks(self):
        self.udin.service_remarks = "Fee for issuing certificate for Form 146 FILOPA 20260502."
        self.udin.save()
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "date_of_signing_of_document": "02-05-2026",
                "service_remarks": "",
                "derive_service_fy": "1",
            },
        )
        self.assertIn(response.status_code, (200, 302))
        self.udin.refresh_from_db()
        self.assertEqual(self.udin.ay_fy, "FY27")
        self.assertEqual(
            self.udin.service_remarks,
            "Fee for issuing certificate for Form 146 FILOPA 20260502.",
        )

    def test_update_service_fy_does_not_clear_existing_client_service(self):
        self.udin.client = self.client_row
        self.udin.service = self.cert
        self.udin.save()
        url = reverse("udin_edit", kwargs={"pk": self.udin.pk})
        response = self.client.post(
            url,
            {
                "udin": self.udin.udin,
                "remarks": self.udin.remarks,
                "date_of_signing_of_document": "02-05-2026",
                "client": "",
                "service": "",
                "ay_fy": "2026-2027",
                "derive_service_fy": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.udin.refresh_from_db()
        self.assertEqual(self.udin.ay_fy, "FY27")
        self.assertEqual(self.udin.client_id, self.client_row.pk)
        self.assertEqual(self.udin.service_id, self.cert.pk)
