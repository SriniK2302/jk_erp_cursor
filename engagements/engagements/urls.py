from django.urls import path

from engagements import views

urlpatterns = [
    path("engagements/", views.engagements, name="engagements"),
    path(
        "engagements/teams/bulk/",
        views.bulk_engagement_team_assignments,
        name="bulk_engagement_team_assignments",
    ),
    path("engagements/new/", views.engagement_create, name="engagement_create"),
    path("engagements/<int:pk>/edit/", views.engagement_edit, name="engagement_edit"),
    path(
        "engagements/<int:engagement_pk>/schedules/",
        views.engagement_schedules,
        name="engagement_schedules",
    ),
    path(
        "engagements/<int:engagement_pk>/schedules/new/",
        views.engagement_schedule_create,
        name="engagement_schedule_create",
    ),
    path(
        "engagements/<int:engagement_pk>/schedules/<int:pk>/edit/",
        views.engagement_schedule_edit,
        name="engagement_schedule_edit",
    ),
    path(
        "engagements/<int:engagement_pk>/teams/",
        views.engagement_team_assignments,
        name="engagement_team_assignments",
    ),
    path(
        "engagements/<int:engagement_pk>/teams/new/",
        views.engagement_team_assignment_create,
        name="engagement_team_assignment_create",
    ),
    path(
        "engagements/<int:engagement_pk>/teams/<int:pk>/edit/",
        views.engagement_team_assignment_edit,
        name="engagement_team_assignment_edit",
    ),
    path(
        "engagements/<int:engagement_pk>/status-remarks/",
        views.engagement_status_remarks,
        name="engagement_status_remarks",
    ),
    path(
        "engagements/<int:engagement_pk>/work-area-notes-all/",
        views.engagement_all_work_area_notes,
        name="engagement_all_work_area_notes",
    ),
]
