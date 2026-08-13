from django.urls import path

from . import views

urlpatterns = [
    path("", views.setup_users, name="setup_users"),
    path("<int:pk>/edit/", views.setup_user_edit, name="setup_user_edit"),
    path("team-member-search/", views.team_member_search_json, name="team_member_search"),
]
