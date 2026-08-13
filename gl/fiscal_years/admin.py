from django.contrib import admin

from .models import FiscalYear


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ("fy_no", "start_date", "end_date", "created_by", "created_on", "updated_on")
    search_fields = ("fy_no",)
