from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("config", "0016_alter_smtpmailsettings_smtp_host"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="additional_mail_ids",
            field=models.TextField(blank=True, default=""),
        ),
    ]
