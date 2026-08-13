from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0050_merge_status_remarks_into_audit_queries"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagement",
            name="additional_mail_ids",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="engagement",
            name="engagement_mail_id",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
