from django.urls import path

from . import views

urlpatterns = [
    path("", views.service_engagement_checklists, name="engagement_checklist_templates"),
]
