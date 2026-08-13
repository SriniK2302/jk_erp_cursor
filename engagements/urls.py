from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.manage_engagements, name="manage_engagements"),
    path("certification-fees/", views.certification_fees, name="certification_fees"),
    path("certification-fees/new/", views.certification_fee_create, name="certification_fee_create"),
    path(
        "certification-fees/<int:pk>/edit/",
        views.certification_fee_edit,
        name="certification_fee_edit",
    ),
    path(
        "session-engagement/set/",
        views.session_engagement_set,
        name="session_engagement_set",
    ),
    path(
        "session-engagement/clear/",
        views.session_engagement_clear,
        name="session_engagement_clear",
    ),
    path(
        "team-assignments-report/",
        views.team_assignments_report,
        name="team_assignments_report",
    ),
    path(
        "status-remarks-report/",
        views.status_remarks_report,
        name="status_remarks_report",
    ),
    path(
        "work-area-notes-report/",
        views.work_area_notes_report,
        name="work_area_notes_report",
    ),
    path(
        "audit-queries-report/",
        views.audit_queries_report,
        name="audit_queries_report",
    ),
    path(
        "work-area-notes/<int:query_pk>/draft-mail/",
        views.audit_query_open_draft,
        name="audit_query_open_draft",
    ),
    path("", include("engagements.timesheets.urls")),
    path("", include("engagements.engagements.urls")),
    path("", include("engagements.work_areas.urls")),
    path("", include("engagements.engagement_divisions.urls")),
    path("documentations/", include("engagements.documentations.urls")),
    path(
        "service-engagement-checklists/",
        include("engagements.checklists.urls"),
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/",
        views.engagement_documentation_maps,
        name="engagement_documentation_maps",
    ),
    path(
        "engagements/<int:engagement_pk>/documentation-options/search/",
        views.engagement_documentation_option_search,
        name="engagement_documentation_option_search",
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/new/",
        views.engagement_documentation_map_create,
        name="engagement_documentation_map_create",
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/<int:pk>/edit/",
        views.engagement_documentation_map_edit,
        name="engagement_documentation_map_edit",
    ),
    path(
        "engagements/<int:engagement_pk>/uploaded-documents/",
        views.engagement_uploaded_documents_report,
        name="engagement_uploaded_documents_report",
    ),
    path(
        "engagements/<int:engagement_pk>/documents-and-notes/",
        views.engagement_documents_and_notes,
        name="engagement_documents_and_notes",
    ),
    path(
        "engagements/<int:engagement_pk>/documentation-missing-uploads/",
        views.engagement_documentation_missing_uploads_report,
        name="engagement_documentation_missing_uploads_report",
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/<int:map_pk>/files/",
        views.engagement_documentation_map_files,
        name="engagement_documentation_map_files",
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/<int:map_pk>/filled-template.docx",
        views.engagement_documentation_map_word_filled_download,
        name="engagement_documentation_map_word_filled_download",
    ),
    path(
        "engagements/<int:engagement_pk>/documentations/<int:map_pk>/attachments/<int:pk>/download/",
        views.engagement_documentation_attachment_download,
        name="engagement_documentation_attachment_download",
    ),
]
