from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0052_engagementdivision_mail_ids"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditQueryMailDraftLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("recipient_to", models.TextField(blank=True, default="")),
                ("recipient_cc", models.TextField(blank=True, default="")),
                ("subject", models.CharField(max_length=255)),
                ("drafted_on", models.DateTimeField(auto_now_add=True)),
                (
                    "audit_query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_draft_logs",
                        to="engagements.auditquery",
                    ),
                ),
                (
                    "drafted_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_audit_query_mail_drafts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "audit_query_mail_draft_logs",
                "ordering": ["-drafted_on", "-id"],
            },
        ),
    ]
