from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0048_auditquery_amount_unit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditquery",
            name="amount_unit",
            field=models.CharField(
                choices=[("crores", "Crores"), ("lakhs", "Lakhs"), ("rs", "Rs")],
                default="lakhs",
                max_length=20,
            ),
        ),
    ]
