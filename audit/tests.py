from django.contrib.auth import get_user_model
from django.test import TestCase

from sales.client_classifications.models import ClientClassification
from sales.clients.models import Client

from .context import clear_audit_user, set_audit_user
from .models import AuditLog


class AuditTrailTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.actor = User.objects.create_user("auditor", "a@example.com", "pass")
        self.classification, _ = ClientClassification.objects.get_or_create(
            classification_name="Others",
            defaults={"created_by": self.actor},
        )
        self.biz_client = Client.objects.create(
            client_name="Acme",
            client_short_name="Acme",
            client_code="ACME",
            classification=self.classification,
            is_active=True,
            created_by=self.actor,
        )

    def test_update_creates_audit_row(self):
        set_audit_user(self.actor)
        try:
            self.biz_client.client_name = "Acme Ltd"
            self.biz_client.save()
        finally:
            clear_audit_user()

        log = AuditLog.objects.get(action=AuditLog.Action.UPDATE, object_id=str(self.biz_client.pk))
        self.assertEqual(log.model_label, "config.Client")
        self.assertEqual(log.actor, self.actor)
        self.assertEqual(log.before_json["client_name"], "Acme")
        self.assertEqual(log.after_json["client_name"], "Acme Ltd")

    def test_delete_creates_audit_row(self):
        pk = self.biz_client.pk
        set_audit_user(self.actor)
        try:
            self.biz_client.delete()
        finally:
            clear_audit_user()

        log = AuditLog.objects.get(action=AuditLog.Action.DELETE, object_id=str(pk))
        self.assertEqual(log.model_label, "config.Client")
        self.assertEqual(log.before_json["client_code"], "ACME")
        self.assertIsNone(log.after_json)
