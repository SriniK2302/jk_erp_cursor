from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "model_label",
        "object_id",
        "object_repr",
        "actor",
    )
    list_filter = ("action", "model_label")
    search_fields = ("object_id", "object_repr", "model_label")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "action",
        "model_label",
        "object_id",
        "object_repr",
        "before_json",
        "after_json",
        "actor",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
