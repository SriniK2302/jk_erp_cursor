from django.apps import AppConfig


class JournalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gl.journal"
    label = "gl_journal"
    verbose_name = "General ledger journal"
