# Generated manually for filled Word download labels.

from django.db import migrations, models


def preset_mr01_company_policy(apps, schema_editor):
    EngagementDocumentation = apps.get_model("engagements", "EngagementDocumentation")
    for row in EngagementDocumentation.objects.all():
        sd = (row.standard_document or "").lower()
        if (
            "management representation" in sd
            and "company policy" in sd
            and not (row.filled_download_label or "").strip()
        ):
            row.filled_download_label = "MR 01"
            row.save(update_fields=["filled_download_label"])


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0066_engagement_fee_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdocumentation",
            name="filled_download_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional short suffix for Fill Word downloads, after date · FY · client code · service code (e.g. MR 01). Leave blank to build a short name from the standard document.",
                max_length=32,
            ),
        ),
        migrations.RunPython(preset_mr01_company_policy, migrations.RunPython.noop),
    ]
