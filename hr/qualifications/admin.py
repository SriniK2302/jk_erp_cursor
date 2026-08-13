from django.contrib import admin

from .models import Qualification


@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display = (
        "qualification_desc",
        "qualification_code",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = ("qualification_desc", "qualification_code")
