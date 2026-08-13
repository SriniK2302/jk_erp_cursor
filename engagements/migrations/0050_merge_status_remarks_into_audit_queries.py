from django.db import migrations, models


def forward_merge_status_remarks(apps, schema_editor):
    AuditQuery = apps.get_model("engagements", "AuditQuery")
    EngagementWorkAreaStatusRemark = apps.get_model(
        "engagements", "EngagementWorkAreaStatusRemark"
    )
    DivisionWorkAreaStatusRemark = apps.get_model(
        "engagements", "DivisionWorkAreaStatusRemark"
    )

    for row in EngagementWorkAreaStatusRemark.objects.all().iterator():
        remarks = (row.remarks or "").strip()
        subject = (remarks[:120] or "Status update").strip()
        AuditQuery.objects.create(
            engagement_work_area_id=row.work_area_id,
            query_date=row.remark_date,
            entry_type="status",
            subject=subject,
            query_text=remarks,
            response_expected_from="internal",
            status="closed",
            created_by_id=row.created_by_id,
        )

    for row in DivisionWorkAreaStatusRemark.objects.all().iterator():
        remarks = (row.remarks or "").strip()
        subject = (remarks[:120] or "Status update").strip()
        AuditQuery.objects.create(
            division_work_area_id=row.work_area_id,
            query_date=row.remark_date,
            entry_type="status",
            subject=subject,
            query_text=remarks,
            response_expected_from="internal",
            status="closed",
            created_by_id=row.created_by_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0049_alter_auditquery_amount_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditquery",
            name="entry_type",
            field=models.CharField(
                choices=[("query", "Query"), ("status", "Status")],
                default="query",
                max_length=20,
            ),
        ),
        migrations.RunPython(forward_merge_status_remarks, migrations.RunPython.noop),
    ]
