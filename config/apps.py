from django.apps import AppConfig


class ConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config"

    def ready(self):
        from django.contrib import admin
        from django.contrib.auth.models import User

        from .admin import UserAdmin

        if admin.site.is_registered(User):
            admin.site.unregister(User)
        admin.site.register(User, UserAdmin)
