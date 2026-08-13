from django.urls import path

from engagements import views

urlpatterns = [
    path("divisions/", views.engagement_divisions, name="engagement_divisions"),
    path(
        "divisions/schedule-bounds/<int:engagement_pk>/",
        views.engagement_schedule_bounds_json,
        name="engagement_schedule_bounds",
    ),
    path("divisions/new/", views.engagement_division_create, name="engagement_division_create"),
    path(
        "divisions/<int:pk>/edit/",
        views.engagement_division_edit,
        name="engagement_division_edit",
    ),
    path(
        "divisions/<int:division_pk>/teams/",
        views.engagement_division_team_assignments,
        name="engagement_division_team_assignments",
    ),
    path(
        "divisions/<int:division_pk>/teams/new/",
        views.engagement_division_team_assignment_create,
        name="engagement_division_team_assignment_create",
    ),
    path(
        "divisions/<int:division_pk>/teams/<int:pk>/edit/",
        views.engagement_division_team_assignment_edit,
        name="engagement_division_team_assignment_edit",
    ),
    path(
        "divisions/<int:division_pk>/status-remarks/",
        views.engagement_division_status_remarks,
        name="engagement_division_status_remarks",
    ),
    path(
        "divisions/<int:division_pk>/documentations/",
        views.engagement_division_documentation_maps,
        name="engagement_division_documentation_maps",
    ),
    path(
        "divisions/<int:division_pk>/documentation-options/search/",
        views.engagement_division_documentation_option_search,
        name="engagement_division_documentation_option_search",
    ),
    path(
        "divisions/<int:division_pk>/documentations/new/",
        views.engagement_division_documentation_map_create,
        name="engagement_division_documentation_map_create",
    ),
    path(
        "divisions/<int:division_pk>/documentations/<int:pk>/edit/",
        views.engagement_division_documentation_map_edit,
        name="engagement_division_documentation_map_edit",
    ),
    path(
        "divisions/<int:division_pk>/uploaded-documents/",
        views.engagement_division_uploaded_documents_report,
        name="engagement_division_uploaded_documents_report",
    ),
    path(
        "divisions/<int:division_pk>/documentations/<int:map_pk>/files/",
        views.engagement_division_documentation_map_files,
        name="engagement_division_documentation_map_files",
    ),
    path(
        "divisions/<int:division_pk>/documentations/<int:map_pk>/attachments/<int:pk>/download/",
        views.engagement_division_documentation_attachment_download,
        name="engagement_division_documentation_attachment_download",
    ),
]
