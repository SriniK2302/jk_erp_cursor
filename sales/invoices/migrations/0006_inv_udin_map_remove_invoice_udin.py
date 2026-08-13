# Generated manually for inv_udin_map + InvoiceLine.line_description; drops Invoice.udin.

import django.db.models.deletion
from django.db import migrations, models


def forwards_copy_udin_to_map(apps, schema_editor):
    Invoice = apps.get_model("invoices", "Invoice")
    InvUdinMap = apps.get_model("invoices", "InvUdinMap")
    for inv in Invoice.objects.exclude(udin_id=None).select_related("service"):
        desc = ""
        if inv.service_id:
            desc = (getattr(inv.service, "service_desc", None) or "")[:255]
        InvUdinMap.objects.create(
            invoice_id=inv.pk,
            line_no=1,
            udin_id=inv.udin_id,
            service_desc=desc,
            line_amount=inv.inv_taxable_value,
        )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0005_invoice_narration"),
        ("udins", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceline",
            name="line_description",
            field=models.CharField(
                blank=True,
                default="",
                help_text="For Service lines: printed description; tax lines leave blank.",
                max_length=255,
            ),
        ),
        migrations.CreateModel(
            name="InvUdinMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_no", models.PositiveSmallIntegerField(help_text="Fee line number (matches Service line order in invoice_lines).")),
                ("service_desc", models.CharField(blank=True, default="", help_text="Description printed for this fee line (e.g. Fee for …).", max_length=255)),
                ("line_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inv_udin_maps",
                        to="invoices.invoice",
                    ),
                ),
                (
                    "udin",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_udin_map_entries",
                        to="udins.udin",
                    ),
                ),
            ],
            options={
                "db_table": "inv_udin_map",
                "ordering": ["invoice_id", "line_no"],
            },
        ),
        migrations.AddConstraint(
            model_name="invudinmap",
            constraint=models.UniqueConstraint(fields=("invoice", "line_no"), name="uq_inv_udin_map_invoice_line"),
        ),
        migrations.RunPython(forwards_copy_udin_to_map, backwards_noop),
        migrations.RemoveConstraint(
            model_name="invoice",
            name="uq_invoice_udin_when_set",
        ),
        migrations.RemoveField(
            model_name="invoice",
            name="udin",
        ),
    ]
