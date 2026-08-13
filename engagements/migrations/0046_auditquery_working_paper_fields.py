from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0045_auditquery_auditqueryresponse"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditquery",
            name="converted_on",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="auditquery",
            name="converted_to_working_paper",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="auditquery",
            name="working_paper_no",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
