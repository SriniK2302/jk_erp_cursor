from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import engagements.models


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0053_auditquerymaildraftlog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditQueryAttachment",
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
                ("file", models.FileField(upload_to=engagements.models._audit_query_attachment_upload_to)),
                ("original_filename", models.CharField(max_length=255)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_audit_query_attachments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="engagements.auditquery",
                    ),
                ),
            ],
            options={
                "db_table": "audit_query_attachments",
                "ordering": ["-created_on", "original_filename", "pk"],
            },
        ),
    ]
