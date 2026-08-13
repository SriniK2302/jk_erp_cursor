from django.db import migrations, models
from django.utils import timezone


def set_documentation_dates(apps, schema_editor):
    EngagementDocumentationMap = apps.get_model(
        "engagements", "EngagementDocumentationMap"
    )
    for m in EngagementDocumentationMap.objects.all().iterator():
        created = m.created_on
        if created is None:
            d = timezone.localdate()
        elif timezone.is_aware(created):
            d = timezone.localtime(created).date()
        else:
            d = created.date()
        EngagementDocumentationMap.objects.filter(pk=m.pk).update(
            documentation_date=d
        )


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0017_team_assignment_multiple_date_ranges"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdocumentationmap",
            name="documentation_date",
            field=models.DateField(
                help_text=(
                    "Date used to order mapped documentation (e.g. planned or signed date)."
                ),
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(set_documentation_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="engagementdocumentationmap",
            name="documentation_date",
            field=models.DateField(
                help_text=(
                    "Date used to order mapped documentation (e.g. planned or signed date)."
                ),
            ),
        ),
    ]
