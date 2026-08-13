"""
Backfill Invoice.narration when blank, using the same UDIN-template synthesis as save / GSTR1.

  python manage.py backfill_invoice_narration
  python manage.py backfill_invoice_narration --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import TextField, Value
from django.db.models.functions import Coalesce, Trim

from sales.invoices.models import Invoice
from sales.invoices.narration_build import header_narration_from_udin_rows


class Command(BaseCommand):
    help = "Set invoice header narration from UDIN maps where narration is currently blank."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        blank = Coalesce(
            Trim("narration"),
            Value("", output_field=TextField()),
            output_field=TextField(),
        )
        qs = (
            Invoice.objects.annotate(_nar_blank=blank)
            .filter(_nar_blank="")
            .prefetch_related("inv_udin_maps__udin__service")
            .order_by("id")
        )
        total = qs.count()
        applied = 0
        skipped_no_maps = 0
        skipped_no_text = 0

        for inv in qs.iterator(chunk_size=200):
            maps = list(inv.inv_udin_maps.order_by("line_no"))
            if not maps:
                skipped_no_maps += 1
                continue
            rows = [
                (m.udin, (m.service_desc or "").strip(), m.line_amount)
                for m in maps
                if m.udin_id
            ]
            if not rows:
                skipped_no_maps += 1
                continue
            text = header_narration_from_udin_rows(rows).strip()
            if not text:
                skipped_no_text += 1
                continue
            if dry:
                self.stdout.write(
                    f"[dry-run] id={inv.pk} no={inv.invoice_no!r} -> {text[:120]!r}"
                    + ("..." if len(text) > 120 else "")
                )
            else:
                with transaction.atomic():
                    Invoice.objects.filter(pk=inv.pk).update(narration=text)
                applied += 1

        if dry:
            would = total - skipped_no_maps - skipped_no_text
            self.stdout.write(
                self.style.WARNING(
                    f"Invoices with blank narration (scanned): {total}\n"
                    f"Would update: {would}\n"
                    f"Skipped (no UDIN maps): {skipped_no_maps}\n"
                    f"Skipped (no template text): {skipped_no_text}\n"
                    "Mode: DRY RUN (no database writes)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Invoices with blank narration (scanned): {total}\n"
                    f"Updated: {applied}\n"
                    f"Skipped (no UDIN maps): {skipped_no_maps}\n"
                    f"Skipped (no template text): {skipped_no_text}\n"
                    "Mode: APPLIED"
                )
            )
