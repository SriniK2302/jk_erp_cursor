from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client, ClientDocument, ClientTaxProfile

from .forms import ClientForm, ClientTaxProfileForm


class ClientDisplayNameTests(TestCase):
    def test_display_name_prefers_short_name(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="display_name_user",
            password="pass12345",
        )
        classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        client = Client.objects.create(
            client_name="Ramco Systems Limited",
            client_short_name="Ramco Systems",
            client_code="RSL1",
            classification=classification,
            created_by=user,
        )
        self.assertEqual(client.display_name, "Ramco Systems")

    def test_display_name_ignores_short_name_when_it_matches_code(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="display_name_code_user",
            password="pass12345",
        )
        classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        client = Client.objects.create(
            client_name="Ramco Systems Limited",
            client_short_name="RSL",
            client_code="RSL1",
            classification=classification,
            created_by=user,
        )
        self.assertEqual(client.display_name, "Ramco Systems")

    def test_display_name_falls_back_to_full_name(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="display_name_fallback_user",
            password="pass12345",
        )
        classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": user},
        )
        client = Client.objects.create(
            client_name="Kavin Engineering and Services Private Limited",
            client_short_name="",
            client_code="KAV1",
            classification=classification,
            created_by=user,
        )
        self.assertEqual(
            client.display_name,
            "Kavin Engineering and Services",
        )


class ClientFormTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="client_form_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Private Limited Company",
            defaults={"created_by": self.user},
        )

    def test_client_code_is_trimmed_uppercased_and_limited(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": " abcd ",
                "classification": self.classification.pk,
                "is_active": True,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_code"], "ABCD")

    def test_common_word_code_is_sanitized(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": "this",
                "classification": self.classification.pk,
                "is_active": True,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_code"], "THIX")

    def test_classification_is_required(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": "acm1",
                "classification": "",
                "is_active": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("classification", form.errors)

    def test_gst_invoicing_fields_are_trimmed(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": "acm1",
                "classification": self.classification.pk,
                "address_1": "  Line 1  ",
                "address_2": "  Line 2  ",
                "area": "  Anna Nagar  ",
                "city_state_pincode": "  Chennai  ",
                "state": "  Tamil Nadu  ",
                "pincode": "  600001  ",
                "contact_person": "  John Doe  ",
                "mail_id": "  accounts@acme.com  ",
                "billing_gstn": "  33ABCDE1234F1Z5  ",
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["address_1"], "Line 1")
        self.assertEqual(form.cleaned_data["address_2"], "Line 2")
        self.assertEqual(form.cleaned_data["area"], "Anna Nagar")
        self.assertEqual(form.cleaned_data["city_state_pincode"], "Chennai")
        self.assertEqual(form.cleaned_data["state"], "Tamil Nadu")
        self.assertEqual(form.cleaned_data["pincode"], "600001")
        self.assertEqual(form.cleaned_data["contact_person"], "John Doe")
        self.assertEqual(form.cleaned_data["mail_id"], "accounts@acme.com")
        self.assertEqual(form.cleaned_data["billing_gstn"], "33ABCDE1234F1Z5")

    def test_additional_mail_ids_are_validated_and_normalized(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": "acm1",
                "classification": self.classification.pk,
                "mail_id": "accounts@acme.com",
                "additional_mail_ids": " a@acme.com ; b@acme.com\nc@acme.com ",
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["additional_mail_ids"],
            "a@acme.com, b@acme.com, c@acme.com",
        )

    def test_additional_mail_ids_reject_invalid_items(self):
        form = ClientForm(
            data={
                "client_name": "Acme Pvt Ltd",
                "client_short_name": "Acme",
                "client_code": "acm1",
                "classification": self.classification.pk,
                "additional_mail_ids": "ok@acme.com, not-an-email",
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("additional_mail_ids", form.errors)


class ClientTaxProfileFormTests(TestCase):
    def test_pan_is_uppercased_and_validated(self):
        form = ClientTaxProfileForm(
            data={
                "pan": "abcde1234f",
                "tax_password": "secret",
                "date_of_formation": "2020-01-01",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["pan"], "ABCDE1234F")

    def test_pan_format_invalid(self):
        form = ClientTaxProfileForm(
            data={
                "pan": "bad123",
                "tax_password": "",
                "date_of_formation": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("pan", form.errors)


class ClientTaxProfileViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="client_tax_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Tax Profile Client",
            client_short_name="TPC",
            client_code="TPC1",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )

    def test_create_tax_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("client_tax_profile", args=[self.client_item.pk]),
            {
                "pan": "ABCDE1234F",
                "tax_password": "pwd-123",
                "date_of_formation": "2018-05-20",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = ClientTaxProfile.objects.get(client=self.client_item)
        self.assertEqual(profile.pan, "ABCDE1234F")
        self.assertEqual(profile.tax_password, "pwd-123")


class ClientDocumentTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="client_doc_user",
            password="pass12345",
        )
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Private Limited Company",
            defaults={"created_by": self.user},
        )
        self.client_item = Client.objects.create(
            client_name="Doc Client Ltd",
            client_short_name="Doc Client",
            client_code="DOCL",
            classification=self.classification,
            is_active=True,
            created_by=self.user,
        )

    def test_upload_and_list_documents(self):
        self.client.force_login(self.user)
        url = reverse("client_documents", args=[self.client_item.pk])
        response = self.client.post(
            url,
            {
                "action": "upload_document",
                "document_label": "MOA",
                "notes": "Memorandum of association",
                "files": [
                    SimpleUploadedFile("moa.pdf", b"%PDF-1.4", content_type="application/pdf"),
                    SimpleUploadedFile("aoa.docx", b"docx", content_type="application/octet-stream"),
                ],
            },
        )
        self.assertEqual(response.status_code, 302)
        docs = ClientDocument.objects.filter(client=self.client_item).order_by("pk")
        self.assertEqual(docs.count(), 2)
        self.assertEqual(docs[0].document_label, "MOA")
        self.assertEqual(docs[0].notes, "Memorandum of association")
        self.assertEqual(docs[0].original_filename, "moa.pdf")

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "MOA")
        self.assertContains(page, "moa.pdf")
        self.assertContains(page, "aoa.docx")

    def test_download_document(self):
        doc = ClientDocument.objects.create(
            client=self.client_item,
            file=SimpleUploadedFile("board.pdf", b"pdf", content_type="application/pdf"),
            original_filename="board.pdf",
            document_label="Board resolution",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "client_document_download",
                args=[self.client_item.pk, doc.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="board.pdf"')

    def test_open_inline_pdf(self):
        doc = ClientDocument.objects.create(
            client=self.client_item,
            file=SimpleUploadedFile("summary.pdf", b"pdf", content_type="application/pdf"),
            original_filename="summary.pdf",
            created_by=self.user,
        )
        self.assertTrue(doc.can_open_inline)
        self.client.force_login(self.user)
        url = (
            reverse(
                "client_document_download",
                args=[self.client_item.pk, doc.pk],
            )
            + "?disposition=inline"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('inline; filename="summary.pdf"', response["Content-Disposition"])

    def test_delete_document(self):
        doc = ClientDocument.objects.create(
            client=self.client_item,
            file=SimpleUploadedFile("temp.txt", b"hi", content_type="text/plain"),
            original_filename="temp.txt",
            created_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("client_documents", args=[self.client_item.pk]),
            {"action": "delete_document", "pk": doc.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ClientDocument.objects.filter(pk=doc.pk).exists())
