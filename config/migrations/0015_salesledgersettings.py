from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("config", "0014_client_invoice_tax_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesLedgerSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("updated_on", models.DateTimeField(auto_now=True)),
                (
                    "cgst_output_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="config.chartofaccount",
                    ),
                ),
                (
                    "igst_output_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="config.chartofaccount",
                    ),
                ),
                (
                    "sales_ledger_control_account",
                    models.ForeignKey(
                        blank=True,
                        help_text="Receivables control account for invoice posting.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="config.chartofaccount",
                    ),
                ),
                (
                    "service_income_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="config.chartofaccount",
                    ),
                ),
                (
                    "sgst_output_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="config.chartofaccount",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sales ledger settings",
                "db_table": "sales_ledger_settings",
            },
        ),
    ]
