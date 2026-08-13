from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0067_engagementdocumentation_filled_download_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdocumentationmap",
            name="representation_point_matrix",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Per-engagement acknowledgment matrix for MR 02 (and similar) items: point id → {status, notes?}. Empty when not used.",
            ),
        ),
    ]
