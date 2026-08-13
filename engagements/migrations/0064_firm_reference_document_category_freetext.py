from django.db import migrations, models

# Values stored before this migration used choice *values* (slugs).
_SLUG_TO_LABEL = {
    "audit_methodology": "Audit methodology",
    "tax": "Tax",
    "it_tools": "IT & tools",
    "firm_policies": "Firm policies",
    "templates_non_client": "Templates (non-client-specific)",
    "external_standards": "External standards & circulars",
    "general": "General / other",
}


def forwards_slug_to_label(apps, schema_editor):
    FirmReferenceDocument = apps.get_model("engagements", "FirmReferenceDocument")
    for row in FirmReferenceDocument.objects.all().iterator():
        raw = (row.category or "").strip()
        new_cat = _SLUG_TO_LABEL.get(raw, raw)
        if not new_cat:
            new_cat = "General / other"
        new_cat = new_cat[:100]
        if new_cat != row.category:
            row.category = new_cat
            row.save(update_fields=["category"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0063_firm_reference_document"),
    ]

    operations = [
        migrations.AlterField(
            model_name="firmreferencedocument",
            name="category",
            field=models.CharField(
                db_index=True,
                default="General / other",
                max_length=100,
            ),
        ),
        migrations.RunPython(forwards_slug_to_label, noop_reverse),
    ]
