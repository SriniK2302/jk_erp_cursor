from django.urls import path

from . import views

urlpatterns = [
    path("", views.udins, name="udins"),
    path("bulk-invoice-zip/", views.bulk_invoice_zip_download, name="bulk_invoice_zip_download"),
    path("new/", views.udin_create, name="udin_create"),
    path("<int:pk>/edit/", views.udin_edit, name="udin_edit"),
    path("certification-fees/", views.certification_fee_rates, name="certification_fee_rates"),
    path(
        "certification-fees/new/",
        views.certification_fee_rate_create,
        name="certification_fee_rate_create",
    ),
    path(
        "certification-fees/<int:pk>/edit/",
        views.certification_fee_rate_edit,
        name="certification_fee_rate_edit",
    ),
]
