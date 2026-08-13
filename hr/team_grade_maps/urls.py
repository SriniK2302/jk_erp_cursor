from django.urls import path

from . import views

urlpatterns = [
    path("defaults/", views.team_grade_map_defaults, name="team_grade_map_defaults"),
    path("", views.team_grade_maps, name="team_grade_maps"),
    path("new/", views.team_grade_map_create, name="team_grade_map_create"),
    path("<int:pk>/edit/", views.team_grade_map_edit, name="team_grade_map_edit"),
]
