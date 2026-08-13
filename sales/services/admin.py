from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("service_desc", "service_code", "created_by", "created_on", "updated_on")
    search_fields = ("service_desc", "service_code")
