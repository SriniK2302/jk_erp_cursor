from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0046_auditquery_working_paper_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditquery",
            name="amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
    ]
