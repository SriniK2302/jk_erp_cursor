from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("config", "0015_salesledgersettings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="smtpmailsettings",
            name="smtp_host",
            field=models.CharField(
                default="smtppro.zoho.com",
                help_text="Zoho Mail: smtppro.zoho.com (organisation) or smtp.zoho.com (personal).",
                max_length=120,
            ),
        ),
    ]
