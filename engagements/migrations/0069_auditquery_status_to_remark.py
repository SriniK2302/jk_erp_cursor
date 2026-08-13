from django.db import migrations, models


def forward_status_to_remark(apps, schema_editor):
    AuditQuery = apps.get_model("engagements", "AuditQuery")
    AuditQuery.objects.filter(entry_type="status").update(entry_type="remark")


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0068_engagementdocumentationmap_representation_point_matrix"),
    ]

    operations = [
        migrations.RunPython(forward_status_to_remark, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="auditquery",
            name="entry_type",
            field=models.CharField(
                choices=[("query", "Query"), ("remark", "Remark")],
                default="query",
                max_length=20,
            ),
        ),
    ]
