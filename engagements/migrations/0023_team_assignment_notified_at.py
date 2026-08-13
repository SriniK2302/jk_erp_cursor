from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0022_engagementdocumentationmapattachment_document_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementteamassignment",
            name="notified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When an assignment notification email was last sent to the team member.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="engagementdivisionteamassignment",
            name="notified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When an assignment notification email was last sent to the team member.",
                null=True,
            ),
        ),
    ]
