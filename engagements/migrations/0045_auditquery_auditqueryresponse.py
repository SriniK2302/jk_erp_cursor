from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0044_statusremarks_all_levels"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditQuery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query_date", models.DateField()),
                ("subject", models.CharField(max_length=255)),
                ("query_text", models.TextField()),
                ("response_expected_from", models.CharField(choices=[("internal", "Internal"), ("client", "Client")], default="internal", max_length=20)),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=20)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("updated_on", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_audit_queries", to=settings.AUTH_USER_MODEL)),
                ("division_work_area", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_queries", to="engagements.divisionworkarea")),
                ("engagement_work_area", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_queries", to="engagements.engagementworkarea")),
            ],
            options={
                "db_table": "audit_queries",
                "ordering": ["-query_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="AuditQueryResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("response_date", models.DateField()),
                ("responder_type", models.CharField(choices=[("internal", "Internal"), ("client", "Client")], default="internal", max_length=20)),
                ("response_text", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_audit_query_responses", to=settings.AUTH_USER_MODEL)),
                ("query", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="responses", to="engagements.auditquery")),
            ],
            options={
                "db_table": "audit_query_responses",
                "ordering": ["response_date", "id"],
            },
        ),
    ]
