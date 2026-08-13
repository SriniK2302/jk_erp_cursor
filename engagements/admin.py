from django.contrib import admin

from engagements.documentations.forms import FirmReferenceDocumentForm
from engagements.documentations.map_cleanup import (
    delete_maps_for_removed_setup_classifications,
    notify_documentation_map_cascade,
)

from .models import (
    Engagement,
    EngagementDivision,
    EngagementDivisionDocumentationMap,
    EngagementDivisionTeamAssignment,
    EngagementDocumentation,
    EngagementDocumentationMap,
    EngagementTeamAssignment,
    FirmReferenceDocument,
    DivisionWorkArea,
    DivisionWorkAreaPeriod,
    EngagementSchedule,
    EngagementWorkArea,
    EngagementWorkAreaPeriod,
)


class EngagementScheduleInline(admin.TabularInline):
    model = EngagementSchedule
    extra = 0


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "fiscal_year",
        "service",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "client__client_name",
        "client__client_code",
        "fiscal_year__fy_no",
        "service__service_desc",
        "service__service_code",
    )
    inlines = [EngagementScheduleInline]


@admin.register(EngagementWorkArea)
class EngagementWorkAreaAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "work_area_name",
        "sort_order",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "work_area_name",
        "engagement__client__client_name",
        "engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
    )


@admin.register(EngagementWorkAreaPeriod)
class EngagementWorkAreaPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "work_area",
        "planned_start",
        "planned_finish",
        "actual_start",
        "actual_finish",
        "created_by",
        "created_on",
    )
    search_fields = (
        "work_area__work_area_name",
        "work_area__engagement__client__client_name",
    )


@admin.register(DivisionWorkAreaPeriod)
class DivisionWorkAreaPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "work_area",
        "planned_start",
        "planned_finish",
        "actual_start",
        "actual_finish",
        "created_by",
        "created_on",
    )
    search_fields = (
        "work_area__work_area_name",
        "work_area__division__division_name",
    )


@admin.register(DivisionWorkArea)
class DivisionWorkAreaAdmin(admin.ModelAdmin):
    list_display = (
        "division",
        "work_area_name",
        "sort_order",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "work_area_name",
        "division__division_name",
        "division__engagement__client__client_name",
        "division__engagement__fiscal_year__fy_no",
    )


@admin.register(EngagementSchedule)
class EngagementScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "planned_start",
        "planned_finish",
        "actual_start",
        "actual_finish",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "engagement__client__client_name",
        "engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
    )


@admin.register(EngagementDivision)
class EngagementDivisionAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "division_name",
        "planned_start",
        "planned_finish",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "engagement__client__client_name",
        "engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "division_name",
    )


@admin.register(FirmReferenceDocument)
class FirmReferenceDocumentAdmin(admin.ModelAdmin):
    form = FirmReferenceDocumentForm
    list_display = (
        "title",
        "category",
        "tags",
        "is_active",
        "original_filename",
        "created_by",
        "created_on",
        "updated_on",
    )
    list_filter = ("category", "is_active")
    search_fields = ("title", "description", "original_filename", "tags", "category")
    readonly_fields = ("created_by", "created_on", "updated_on")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EngagementDocumentation)
class EngagementDocumentationAdmin(admin.ModelAdmin):
    list_display = (
        "standard_document",
        "document_stage",
        "classifications_summary",
        "filled_download_label",
        "has_word_template",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "standard_document",
        "filled_download_label",
        "document_stage",
        "applicable_classifications__classification_name",
    )
    filter_horizontal = ("applicable_classifications",)

    @admin.display(description="Word template", boolean=True)
    def has_word_template(self, obj):
        return bool(obj.word_template)

    @admin.display(description="Applicable to")
    def classifications_summary(self, obj):
        return ", ".join(
            obj.applicable_classifications.order_by(
                "classification_name"
            ).values_list("classification_name", flat=True)
        )

    def save_related(self, request, form, formsets, change):
        old_ids = None
        if change and form.instance.pk:
            old_ids = set(
                EngagementDocumentation.objects.get(
                    pk=form.instance.pk
                ).applicable_classifications.values_list("pk", flat=True)
            )
        super().save_related(request, form, formsets, change)
        if old_ids is not None and form.instance.pk:
            new_ids = set(
                form.instance.applicable_classifications.values_list("pk", flat=True)
            )
            removed = old_ids - new_ids
            if removed:
                summary = delete_maps_for_removed_setup_classifications(
                    form.instance, removed
                )
                notify_documentation_map_cascade(request, summary)


@admin.register(EngagementDocumentationMap)
class EngagementDocumentationMapAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "documentation",
        "documentation_date",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "engagement__client__client_name",
        "engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "documentation__standard_document",
        "documentation__document_stage",
    )


@admin.register(EngagementTeamAssignment)
class EngagementTeamAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "team_member",
        "planned_start",
        "planned_finish",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "engagement__client__client_name",
        "engagement__fiscal_year__fy_no",
        "engagement__service__service_desc",
        "team_member__first_name",
        "team_member__last_name",
        "team_member__code",
    )


@admin.register(EngagementDivisionDocumentationMap)
class EngagementDivisionDocumentationMapAdmin(admin.ModelAdmin):
    list_display = (
        "division",
        "documentation",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "division__engagement__client__client_name",
        "division__engagement__fiscal_year__fy_no",
        "division__engagement__service__service_desc",
        "division__division_name",
        "documentation__standard_document",
        "documentation__document_stage",
    )


@admin.register(EngagementDivisionTeamAssignment)
class EngagementDivisionTeamAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "division",
        "team_member",
        "planned_start",
        "planned_finish",
        "created_by",
        "created_on",
        "updated_on",
    )
    search_fields = (
        "division__engagement__client__client_name",
        "division__engagement__fiscal_year__fy_no",
        "division__engagement__service__service_desc",
        "division__division_name",
        "team_member__first_name",
        "team_member__last_name",
        "team_member__code",
    )
