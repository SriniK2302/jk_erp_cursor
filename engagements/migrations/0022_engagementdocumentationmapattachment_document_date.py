from django.db import migrations, models
from django.utils import timezone


def backfill_document_dates(apps, schema_editor):
    Attachment = apps.get_model("engagements", "EngagementDocumentationMapAttachment")
    for att in Attachment.objects.select_related("documentation_map").iterator():
        m = att.documentation_map
        d = getattr(m, "documentation_date", None) if m is not None else None
        if d is None:
            d = timezone.localdate()
        Attachment.objects.filter(pk=att.pk).update(document_date=d)


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0021_noop_check"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdocumentationmapattachment",
            name="document_date",
            field=models.DateField(
                help_text=(
                    "Date of the underlying document (e.g. letter or signing date)."
                ),
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(backfill_document_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="engagementdocumentationmapattachment",
            name="document_date",
            field=models.DateField(
                help_text=(
                    "Date of the underlying document (e.g. letter or signing date)."
                ),
            ),
        ),
        migrations.AlterModelOptions(
            name="engagementdocumentationmapattachment",
            options={
                "ordering": ["-document_date", "original_filename", "pk"],
            },
        ),
    ]
