from django.urls import path

from . import views

urlpatterns = [
    path("", views.bank_transactions_hub, name="bank_transactions_hub"),
    path("build-month-summary/", views.bank_transactions_build_month_summary, 
         name="bank_transactions_build_month_summary"),
    path("build-ym/", views.bank_transactions_build_ym, name="bank_transactions_build_ym"),
    path("summary-report/", views.bank_transactions_summary_report, 
         name="bank_transactions_summary_report"),
    path("summary-report/upload-statement/", views.bank_transactions_summary_upload_statement, 
         name="bank_transactions_summary_upload_statement"),
    path("summary-report/upload-annual-statement/", views.bank_transactions_summary_upload_annual_statement, 
         name="bank_transactions_summary_upload_annual_statement"),
    path("summary-report/update-cb/", views.bank_transactions_summary_update_cb, 
         name="bank_transactions_summary_update_cb"),
    path("summary-report/update-cb-annual/", views.bank_transactions_summary_update_cb_annual, 
         name="bank_transactions_summary_update_cb_annual"),
    path("opening-balances/", views.bank_transactions_source_ob, 
         name="bank_transactions_source_ob"),
    path("opening-balances/new/", views.bank_transactions_source_ob_create, 
         name="bank_transactions_source_ob_create"),
    path("opening-balances/<int:pk>/edit/", views.bank_transactions_source_ob_edit, 
         name="bank_transactions_source_ob_edit"),
    path("accounts/", views.bank_transactions_source_accounts, 
         name="bank_transactions_source_accounts"),
    path("accounts/new/", views.bank_transactions_source_account_create, 
         name="bank_transactions_source_account_create"),
    path("accounts/<int:pk>/edit/", views.bank_transactions_source_account_edit, 
         name="bank_transactions_source_account_edit"),
]
