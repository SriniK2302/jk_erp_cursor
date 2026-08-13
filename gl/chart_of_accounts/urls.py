from django.urls import path

from . import views

urlpatterns = [
    path("", views.chart_of_accounts, name="chart_of_accounts"),
    path("next-code/", views.chart_of_account_next_code, name="chart_of_account_next_code"),
    path("new/", views.chart_of_account_create, name="chart_of_account_create"),
    path("<int:pk>/edit/", views.chart_of_account_edit, name="chart_of_account_edit"),
]
