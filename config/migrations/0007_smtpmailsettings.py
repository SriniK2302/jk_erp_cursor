from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("config", "0006_clientclassification_refactor"),
    ]

    operations = [
        migrations.CreateModel(
            name="SmtpMailSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="When off, no emails are sent (assignment saves still succeed).",
                    ),
                ),
                ("smtp_host", models.CharField(default="smtp.zoho.com", max_length=120)),
                ("smtp_port", models.PositiveIntegerField(default=587)),
                ("use_tls", models.BooleanField(default=True)),
                (
                    "use_ssl",
                    models.BooleanField(
                        default=False,
                        help_text="Use for port 465 (SSL). Do not enable both TLS and SSL.",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        blank=True,
                        help_text="Zoho mailbox address used to authenticate SMTP.",
                        max_length=254,
                    ),
                ),
                (
                    "password",
                    models.CharField(
                        blank=True,
                        help_text="Zoho app-specific or account password (stored in DB; restrict who can edit).",
                        max_length=255,
                    ),
                ),
                (
                    "default_from_email",
                    models.EmailField(
                        blank=True,
                        help_text="From address shown to recipients (often same as username).",
                        max_length=254,
                    ),
                ),
                ("updated_on", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "SMTP mail settings",
                "db_table": "smtp_mail_settings",
            },
        ),
    ]
