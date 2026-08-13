from django.urls import path

from . import views

urlpatterns = [
    path("", views.udins_source, name="udins_source"),
]
