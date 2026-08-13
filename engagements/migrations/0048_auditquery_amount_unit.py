from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0047_auditquery_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditquery",
            name="amount_unit",
            field=models.CharField(
                choices=[
                    ("lakhs", "Lakhs"),
                    ("thousands", "Thousands"),
                    ("units", "Units"),
                    ("crores", "Crores"),
                ],
                default="lakhs",
                max_length=20,
            ),
        ),
    ]
