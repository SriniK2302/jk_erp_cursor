from django.urls import path

from . import views

urlpatterns = [
    path("", views.client_classifications, name="client_classifications"),
    path("new/", views.client_classification_create, name="client_classification_create"),
    path(
        "<int:pk>/edit/",
        views.client_classification_edit,
        name="client_classification_edit",
    ),
]
