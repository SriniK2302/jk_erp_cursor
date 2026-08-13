# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def assign_classification_where_null(apps, schema_editor):
    EngagementDocumentation = apps.get_model("engagements", "EngagementDocumentation")
    ClientClassification = apps.get_model("config", "ClientClassification")

    default = ClientClassification.objects.filter(
        classification_name="Others"
    ).first()
    if default is None:
        default = ClientClassification.objects.order_by("id").first()
    if default is None:
        return

    EngagementDocumentation.objects.filter(
        applicable_classification__isnull=True
    ).update(applicable_classification_id=default.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0008_alter_engagementdocumentation_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            assign_classification_where_null,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="engagementdocumentation",
            name="applicable_classification",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="engagement_documentations",
                to="config.clientclassification",
            ),
        ),
    ]
