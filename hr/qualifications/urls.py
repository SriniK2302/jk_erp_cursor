from django.urls import path

from . import views

urlpatterns = [
    path("", views.qualifications, name="qualifications"),
    path("new/", views.qualification_create, name="qualification_create"),
    path("<int:pk>/edit/", views.qualification_edit, name="qualification_edit"),
]
