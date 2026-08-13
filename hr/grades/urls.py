from django.urls import path

from . import views

urlpatterns = [
    path("", views.grades, name="grades"),
    path("new/", views.grade_create, name="grade_create"),
    path("<int:pk>/edit/", views.grade_edit, name="grade_edit"),
]
