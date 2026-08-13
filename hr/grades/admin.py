from django.contrib import admin

from .models import Grade


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("grade_desc", "grade_code", "created_by", "created_on", "updated_on")
    search_fields = ("grade_desc", "grade_code")
