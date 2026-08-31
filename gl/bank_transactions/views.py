from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BankTransactionSourceObForm
from .models import (
    BankTransactionSource,
    BankTransactionSourceOb,
    BankTransactionSourceSummary,
    SourceBankCashAc,
)
from .services.build_month_summary import build_month_summary
from .services.build_ym import build_ym


@login_required
def bank_transactions_hub(request):
    return render(request, "bank_transactions/bank_transactions_hub.html", {})


@login_required
def bank_transactions_build_month_summary(request):
    if request.method == "POST":
        report = build_month_summary(
            SourceBankCashAc=SourceBankCashAc,
            BankTransactionSource=BankTransactionSource,
            BankTransactionSourceSummary=BankTransactionSourceSummary,
            BankTransactionSourceOb=BankTransactionSourceOb,
        )
        messages.success(
            request,
            f"Build complete. {report.accounts_processed} account(s) processed, "
            f"{report.months_created} month(s) created, {report.months_updated} month(s) refreshed.",
        )
        if report.accounts_needing_ob:
            messages.warning(
                request,
                "Accounts missing an opening balance (skipped): "
                + ", ".join(report.accounts_needing_ob),
            )
        if report.accounts_with_invalid_ym_transactions:
            messages.warning(
                request,
                "Accounts with transactions missing a valid YM (those transactions were skipped): "
                + ", ".join(report.accounts_with_invalid_ym_transactions),
            )
        return redirect("bank_transactions_build_month_summary")

    return render(request, "bank_transactions/bank_transactions_build_month_summary.html", {})


@login_required
def bank_transactions_build_ym(request):
    if request.method == "POST":
        report = build_ym(BankTransactionSource=BankTransactionSource)
        messages.success(
            request,
            f"Build complete. {report.updated_count} transaction(s) had their YM filled in "
            f"(rows with an existing YM were left untouched).",
        )
        return redirect("bank_transactions_build_ym")

    return render(request, "bank_transactions/bank_transactions_build_ym.html", {})


@login_required
def bank_transactions_source_ob(request):

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            ob = get_object_or_404(BankTransactionSourceOb, pk=request.POST.get("pk"))
            ob.delete()
            return redirect("bank_transactions_source_ob")
        return redirect("bank_transactions_source_ob")

    return render(
        request,
        "bank_transactions/bank_transactions_source_ob.html",
        {
            "obs": BankTransactionSourceOb.objects.select_related("source_ac").all(),
        },
    )


def _bank_transactions_source_ob_form_view(request, instance=None):
    if request.method == "POST":
        form = BankTransactionSourceObForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("bank_transactions_source_ob")
    else:
        form = BankTransactionSourceObForm(instance=instance)

    return render(
        request,
        "bank_transactions/bank_transactions_source_ob_form.html",
        {
            "form": form,
            "ob": instance,
        },
    )


@login_required
def bank_transactions_source_ob_create(request):
    return _bank_transactions_source_ob_form_view(request)


@login_required
def bank_transactions_source_ob_edit(request, pk):
    ob = get_object_or_404(BankTransactionSourceOb, pk=pk)
    return _bank_transactions_source_ob_form_view(request, instance=ob)

