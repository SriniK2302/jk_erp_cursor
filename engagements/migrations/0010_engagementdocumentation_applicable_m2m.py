# Generated manually

from collections import defaultdict

from django.db import migrations, models


def migrate_classifications_to_m2m_and_merge(apps, schema_editor):
    EngagementDocumentation = apps.get_model("engagements", "EngagementDocumentation")
    EngagementDocumentationMap = apps.get_model(
        "engagements", "EngagementDocumentationMap"
    )
    EngagementDivisionDocumentationMap = apps.get_model(
        "engagements", "EngagementDivisionDocumentationMap"
    )

    for doc in EngagementDocumentation.objects.all():
        if doc.applicable_classification_id:
            doc.applicable_classifications.add(doc.applicable_classification_id)

    groups = defaultdict(list)
    for doc in EngagementDocumentation.objects.all():
        groups[(doc.standard_document, doc.document_stage)].append(doc)

    for rows in groups.values():
        rows.sort(key=lambda d: d.pk)
        keeper = rows[0]
        class_ids = {r.applicable_classification_id for r in rows if r.applicable_classification_id}
        for r in rows[1:]:
            EngagementDocumentationMap.objects.filter(documentation_id=r.pk).update(
                documentation_id=keeper.pk
            )
            EngagementDivisionDocumentationMap.objects.filter(
                documentation_id=r.pk
            ).update(documentation_id=keeper.pk)
            r.delete()
        keeper.applicable_classifications.set(class_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0009_documentation_classification_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementdocumentation",
            name="applicable_classifications",
            field=models.ManyToManyField(
                related_name="engagement_documentations",
                to="config.clientclassification",
            ),
        ),
        migrations.RunPython(
            migrate_classifications_to_m2m_and_merge,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="engagementdocumentation",
            name="uq_standard_document_stage_classification",
        ),
        migrations.RemoveField(
            model_name="engagementdocumentation",
            name="applicable_classification",
        ),
        migrations.AddConstraint(
            model_name="engagementdocumentation",
            constraint=models.UniqueConstraint(
                fields=("standard_document", "document_stage"),
                name="uq_engagementdocumentation_standard_document_stage",
            ),
        ),
        migrations.AlterModelOptions(
            name="engagementdocumentation",
            options={
                "ordering": ["document_stage", "standard_document"],
            },
        ),
    ]
