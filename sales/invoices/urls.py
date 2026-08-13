from django.urls import path

from . import views

urlpatterns = [
    path("hub/", views.sales_hub, name="sales_hub"),
    path("reports/sales-ledger-tb/", views.reports_sales_ledger_tb, name="invoice_reports_sales_ledger_tb"),
    path("reports/monthly-summary/", views.reports_monthly_summary, name="invoice_reports_monthly_summary"),
    path("reports/gstr1-invoices/", views.reports_gstr1_invoice_list, name="invoice_reports_gstr1_invoices"),
    path("reports/", views.reports_home, name="invoice_reports"),
    path("receipts/", views.receipts_home, name="receipts"),
    path("next-invoice-no/", views.invoice_next_no, name="invoice_next_no"),
    path("new/", views.invoice_create, name="invoice_create"),
    path("<int:pk>/preview/", views.invoice_preview, name="invoice_preview"),
    path("<int:pk>/edit/", views.invoice_edit, name="invoice_edit"),
    path("", views.invoice_list, name="invoices"),
]
