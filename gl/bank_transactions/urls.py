from django.urls import path

from . import views

urlpatterns = [
    path("", views.bank_transactions_hub, name="bank_transactions_hub"),
    path("build-month-summary/", views.bank_transactions_build_month_summary, name="bank_transactions_build_month_summary"),
    path("build-ym/", views.bank_transactions_build_ym, name="bank_transactions_build_ym"),
    path("opening-balances/", views.bank_transactions_source_ob, name="bank_transactions_source_ob"),
    path("opening-balances/new/", views.bank_transactions_source_ob_create, name="bank_transactions_source_ob_create"),
    path("opening-balances/<int:pk>/edit/", views.bank_transactions_source_ob_edit, name="bank_transactions_source_ob_edit"),
]

