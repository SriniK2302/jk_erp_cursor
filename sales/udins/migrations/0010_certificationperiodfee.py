# Certification period fees (from date, to date, fee)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("udins", "0009_udin_unique_table_rule"),
    ]

    operations = [
        migrations.CreateModel(
            name="CertificationPeriodFee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_date", models.DateField()),
                ("to_date", models.DateField()),
                ("fee_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("updated_on", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "udins_certification_period_fees",
                "ordering": ["-from_date", "-to_date", "-id"],
            },
        ),
    ]
