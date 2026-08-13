from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0051_engagement_mail_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdivision",
            name="division_mail_ids",
            field=models.TextField(blank=True, default=""),
        ),
    ]
