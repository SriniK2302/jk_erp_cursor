from django.urls import path

from . import views

urlpatterns = [
    path("", views.services, name="services"),
    path("new/", views.service_create, name="service_create"),
    path("<int:pk>/edit/", views.service_edit, name="service_edit"),
]
