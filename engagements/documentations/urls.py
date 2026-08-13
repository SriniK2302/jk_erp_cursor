from django.urls import path

from . import views

urlpatterns = [
    path("reference/new/", views.reference_document_create, name="reference_document_create"),
    path(
        "reference/<int:pk>/edit/",
        views.reference_document_edit,
        name="reference_document_edit",
    ),
    path(
        "reference/<int:pk>/download/",
        views.reference_document_download,
        name="reference_document_download",
    ),
    path("reference/", views.reference_documents, name="reference_documents"),
    path("", views.engagement_documentations, name="engagement_documentations"),
    path("new/", views.engagement_documentation_create, name="engagement_documentation_create"),
    path(
        "<int:pk>/edit/",
        views.engagement_documentation_edit,
        name="engagement_documentation_edit",
    ),
    path(
        "<int:pk>/word-template/download/",
        views.engagement_documentation_word_template_download,
        name="engagement_documentation_word_template_download",
    ),
]
