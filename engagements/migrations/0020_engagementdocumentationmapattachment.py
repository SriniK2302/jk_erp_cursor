import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils.text import get_valid_filename


def _engagement_documentation_map_upload_to(instance, filename):
    safe = get_valid_filename(filename) or "upload"
    unique = f"{uuid.uuid4().hex}_{safe}"
    mid = instance.documentation_map_id
    eid = instance.documentation_map.engagement_id
    return f"engagement_documentation/{eid}/{mid}/{unique}"


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("engagements", "0019_alter_engagementdocumentationmap_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="EngagementDocumentationMapAttachment",
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
                (
                    "file",
                    models.FileField(upload_to=_engagement_documentation_map_upload_to),
                ),
                ("original_filename", models.CharField(max_length=255)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_engagement_documentation_attachments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "documentation_map",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="engagements.engagementdocumentationmap",
                    ),
                ),
            ],
            options={
                "db_table": "engagement_documentation_map_attachments",
                "ordering": ["created_on", "pk"],
            },
        ),
    ]
