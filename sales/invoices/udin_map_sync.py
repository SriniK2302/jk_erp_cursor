from sales.udins.models import Udin

from .models import InvUdinMap, Invoice


def sync_udin_flags_for_pks(udin_pks: set[int], *, invoice: Invoice | None = None) -> None:
    for pk in udin_pks:
        has = InvUdinMap.objects.filter(udin_id=pk).exists()
        if has:
            update_fields = {"is_invoiced": True}
            if invoice and InvUdinMap.objects.filter(udin_id=pk, invoice_id=invoice.pk).exists():
                update_fields["inv_no"] = invoice.invoice_no
                update_fields["inv_date"] = invoice.invoice_date
            Udin.objects.filter(pk=pk).update(**update_fields)
        else:
            Udin.objects.filter(pk=pk).update(is_invoiced=False, inv_no="", inv_date=None)
