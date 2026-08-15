from django.db import models


class SmtpMailSettings(models.Model):
    """Singleton (pk=1): outbound SMTP (e.g. Zoho) for system emails such as team assignment notices."""

    enabled = models.BooleanField(
        default=False,
        help_text="When off, no emails are sent (assignment saves still succeed).",
    )
    smtp_host = models.CharField(
        max_length=120,
        default="smtppro.zoho.com",
        help_text="Zoho Mail: smtppro.zoho.com (organisation) or smtp.zoho.com (personal).",
    )
    smtp_port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(
        default=False,
        help_text="Use for port 465 (SSL). Do not enable both TLS and SSL.",
    )
    username = models.CharField(
        max_length=254,
        blank=True,
        help_text="Zoho mailbox address used to authenticate SMTP.",
    )
    password = models.CharField(
        max_length=255,
        blank=True,
        help_text="Zoho app-specific or account password (stored in DB; restrict who can edit).",
    )
    default_from_email = models.EmailField(
        max_length=254,
        blank=True,
        help_text="From address shown to recipients (often same as username).",
    )
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "smtp_mail_settings"
        verbose_name = "SMTP mail settings"

    def __str__(self):
        return "SMTP mail settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
