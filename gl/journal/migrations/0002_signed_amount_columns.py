# Generated manually: single signed amount (+ debit, − credit).

from decimal import Decimal

from django.db import migrations, models


def forwards_fill_amounts(apps, schema_editor):
    GlLine = apps.get_model("gl_journal", "GlLine")
    GlHeader = apps.get_model("gl_journal", "GlHeader")
    for row in GlLine.objects.all().iterator():
        d = row.debit or Decimal("0")
        c = row.credit or Decimal("0")
        GlLine.objects.filter(pk=row.pk).update(amount=d - c)
    for row in GlHeader.objects.all().iterator():
        GlHeader.objects.filter(pk=row.pk).update(amount=row.net_debit)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("gl_journal", "0001_initial_gl_header_line"),
    ]

    operations = [
        migrations.AddField(
            model_name="glline",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Signed: debit positive (+), credit negative (−).",
                max_digits=18,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="glheader",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Signed total: debit positive (+), credit negative (−). Usually sum of line amounts (0 if balanced).",
                max_digits=18,
                null=True,
            ),
        ),
        migrations.RunPython(forwards_fill_amounts, noop_reverse),
        migrations.RemoveField(model_name="glline", name="debit"),
        migrations.RemoveField(model_name="glline", name="credit"),
        migrations.RemoveField(model_name="glline", name="net_debit"),
        migrations.RemoveField(model_name="glheader", name="debit_sum"),
        migrations.RemoveField(model_name="glheader", name="credit_sum"),
        migrations.RemoveField(model_name="glheader", name="net_debit"),
        migrations.AlterField(
            model_name="glline",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Signed: debit positive (+), credit negative (−).",
                max_digits=18,
            ),
        ),
        migrations.AlterField(
            model_name="glheader",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Signed total: debit positive (+), credit negative (−). Usually sum of line amounts (0 if balanced).",
                max_digits=18,
            ),
        ),
    ]
