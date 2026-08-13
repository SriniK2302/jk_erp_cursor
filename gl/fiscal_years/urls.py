from django.urls import path

from . import views

urlpatterns = [
    path("", views.fiscal_years, name="fiscal_years"),
    path("new/", views.fiscal_year_create, name="fiscal_year_create"),
    path("<int:pk>/edit/", views.fiscal_year_edit, name="fiscal_year_edit"),
]
