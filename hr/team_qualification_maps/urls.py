from django.urls import path

from . import views

urlpatterns = [
    path("", views.team_qualification_maps, name="team_qualification_maps"),
    path("new/", views.team_qualification_map_create, name="team_qualification_map_create"),
    path(
        "<int:pk>/edit/",
        views.team_qualification_map_edit,
        name="team_qualification_map_edit",
    ),
]
