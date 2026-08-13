from django.urls import path

from . import views

urlpatterns = [
    path("", views.teams, name="teams"),
    path("new/", views.team_member_create, name="team_member_create"),
    path("<int:pk>/edit/", views.team_member_edit, name="team_member_edit"),
    path(
        "<int:member_pk>/roll-periods/new/",
        views.roll_period_create,
        name="roll_period_create",
    ),
    path(
        "<int:member_pk>/roll-periods/<int:pk>/edit/",
        views.roll_period_edit,
        name="roll_period_edit",
    ),
    path(
        "<int:member_pk>/qualification-periods/new/",
        views.qualification_period_create,
        name="qualification_period_create",
    ),
    path(
        "<int:member_pk>/qualification-periods/<int:pk>/edit/",
        views.qualification_period_edit,
        name="qualification_period_edit",
    ),
]
