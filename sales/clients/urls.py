from django.urls import path

from . import views

urlpatterns = [
    path("", views.clients, name="clients"),
    path("nav/search/", views.client_nav_search, name="client_nav_search"),
    path("new/", views.client_create, name="client_create"),
    path("<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("<int:pk>/documents/", views.client_documents, name="client_documents"),
    path(
        "<int:pk>/documents/<int:document_pk>/download/",
        views.client_document_download,
        name="client_document_download",
    ),
    path("<int:pk>/tax-profile/", views.client_tax_profile, name="client_tax_profile"),
]
