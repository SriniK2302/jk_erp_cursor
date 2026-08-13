# Add client to certification period fees (fee varies by client)

import django.db.models.deletion
from django.db import migrations, models


def clear_period_fees(apps, schema_editor):
    apps.get_model("udins", "CertificationPeriodFee").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("config", "0001_initial"),
        ("udins", "0010_certificationperiodfee"),
    ]

    operations = [
        migrations.RunPython(clear_period_fees, migrations.RunPython.noop),
        migrations.AddField(
            model_name="certificationperiodfee",
            name="client",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="certification_period_fees",
                to="config.client",
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="certificationperiodfee",
            options={"ordering": ["client__client_name", "-from_date", "-id"]},
        ),
    ]
