from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import BankTransactionSourceObForm, SourceBankCashAcForm
from .models import (
    BankStatementUpload,
    BankTransactionSource,
    BankTransactionSourceOb,
    BankTransactionSourceSummary,
    SourceBankCashAc,
)
from .services.build_month_summary import build_month_summary
from .services.build_ym import build_ym
from .services.extract_closing_balance import (
    extract_closing_balance,
    extract_closing_balances_for_months,
)
from .services.summary_report import build_summary_report, calendar_months_in_fiscal_year


@login_required
def bank_transactions_summary_report(request):
    from django.utils import timezone

    from gl.fiscal_years.models import FiscalYear

    today = timezone.localdate()
    fiscal_years = list(FiscalYear.objects.all().order_by("fy_no"))
    current_fy = None
    for fy in fiscal_years:
        if fy.start_date <= today <= fy.end_date:
            current_fy = fy
            break

    if request.method == "POST":
        row = get_object_or_404(BankTransactionSourceSummary, pk=request.POST.get("pk"))
        raw = (request.POST.get("cb_from_statement") or "").strip()
        if raw == "":
            row.cb_from_statement = None
        else:
            try:
                row.cb_from_statement = float(raw)
            except ValueError:
                messages.error(request, "Statement CB must be a number.")
                return redirect(f"{request.path}?fy={request.POST.get('fy', '')}")
        row.save(update_fields=["cb_from_statement"])
        messages.success(request, f"Saved statement CB for {row.source_ac_id} {row.ym}.")
        return redirect(f"{request.path}?fy={request.POST.get('fy', '')}")

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    report_rows = []
    if selected_fy is not None:
        report_rows = build_summary_report(
            selected_fy,
            SourceBankCashAc=SourceBankCashAc,
            BankTransactionSourceSummary=BankTransactionSourceSummary,
        )
        latest_uploads = {}
        for upload in BankStatementUpload.objects.filter(fiscal_year=selected_fy).order_by("source_ac_id", "-uploaded_on"):
            if upload.source_ac_id not in latest_uploads:
                latest_uploads[upload.source_ac_id] = upload
        for account in report_rows:
            upload = latest_uploads.get(account.source_ac)
            account.statement_file_url = upload.statement_file.url if upload else None
            account.statement_file_name = upload.statement_file.name.rsplit("/", 1)[-1] if upload else None
            
    return render(
        request,
        "bank_transactions/bank_transactions_summary_report.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "report_rows": report_rows,
            "all_accounts": SourceBankCashAc.objects.all(),
        },
    )

@login_required
def bank_transactions_summary_upload_statement(request):
    from urllib.parse import urlencode

    if request.method != "POST":
        return redirect("bank_transactions_summary_report")

    row = get_object_or_404(BankTransactionSourceSummary, pk=request.POST.get("pk"))
    fy_pk = request.POST.get("fy", "")
    back_url = f"{reverse('bank_transactions_summary_report')}?{urlencode({'fy': fy_pk})}"
    uploaded = request.FILES.get("statement_pdf")

    if uploaded is None:
        messages.error(request, "Choose a PDF file first.")
        return redirect(back_url)

    if not uploaded.name.lower().endswith(".pdf"):
        messages.error(request, "Statement must be a PDF file.")
        return redirect(back_url)

    try:
        amount = extract_closing_balance(uploaded, ym=row.ym)
    except Exception:
        amount = None
        messages.error(
            request,
            f"Could not read {uploaded.name}. It may be a scanned/image PDF. "
            "The file is still saved.",
        )

    fiscal_year = get_object_or_404_fiscal_year(fy_pk)

    # extract_closing_balance() reads the stream to the end; rewind before
    # handing it to the FileField, or the saved copy would come out empty.
    uploaded.seek(0)
    upload = BankStatementUpload.objects.create(
        source_ac=row.source_ac,
        fiscal_year=fiscal_year,
        statement_file=uploaded,
        uploaded_by=request.user if request.user.is_authenticated else None,
    )
    row.statement_upload = upload

    if amount is None:
        row.save(update_fields=["statement_upload"])
        messages.warning(
            request,
            f"Could not find a closing balance in {uploaded.name} for "
            f"{row.source_ac_id} {row.ym}. File saved; enter the amount manually.",
        )
        return redirect(back_url)

    row.cb_from_statement = amount
    row.save(update_fields=["cb_from_statement", "statement_upload"])
    messages.success(
        request,
        f"Auto-filled statement CB {amount:,.2f} for {row.source_ac_id} {row.ym} from {uploaded.name}.",
    )
    return redirect(back_url)


@login_required
def bank_transactions_summary_upload_annual_statement(request):
    from urllib.parse import urlencode

    if request.method != "POST":
        return redirect("bank_transactions_summary_report")

    fy_pk = request.POST.get("fy", "")
    back_url = f"{reverse('bank_transactions_summary_report')}?{urlencode({'fy': fy_pk})}"

    fiscal_year = get_object_or_404_fiscal_year(fy_pk)
    if fiscal_year is None:
        messages.error(request, "Choose a fiscal year first.")
        return redirect(back_url)

    account = SourceBankCashAc.objects.filter(source_ac=request.POST.get("source_ac")).first()
    if account is None:
        messages.error(request, "Choose an account first.")
        return redirect(back_url)

    uploaded = request.FILES.get("statement_pdf")
    if uploaded is None:
        messages.error(request, "Choose a PDF file first.")
        return redirect(back_url)

    if not uploaded.name.lower().endswith(".pdf"):
        messages.error(request, "Statement must be a PDF file.")
        return redirect(back_url)

    months = calendar_months_in_fiscal_year(fiscal_year)
    yms = [m["ym"] for m in months]

    try:
        balances_by_ym = extract_closing_balances_for_months(uploaded, yms)
    except Exception:
        messages.error(
            request,
            f"Could not read {uploaded.name}. It may be a scanned/image PDF.",
        )
        return redirect(back_url)

    uploaded.seek(0)
    upload = BankStatementUpload.objects.create(
        source_ac=account,
        fiscal_year=fiscal_year,
        statement_file=uploaded,
        uploaded_by=request.user if request.user.is_authenticated else None,
    )

    rows = BankTransactionSourceSummary.objects.filter(source_ac=account, ym__in=yms)
    rows_by_ym = {row.ym: row for row in rows}

    filled = []
    missing_row = []
    not_found = []
    for ym in yms:
        row = rows_by_ym.get(ym)
        if row is None:
            missing_row.append(ym)
            continue
        amount = balances_by_ym.get(ym)
        if amount is None:
            not_found.append(ym)
            row.statement_upload = upload
            row.save(update_fields=["statement_upload"])
            continue
        row.cb_from_statement = amount
        row.statement_upload = upload
        row.save(update_fields=["cb_from_statement", "statement_upload"])
        filled.append(ym)

    if filled:
        messages.success(
            request,
            f"Auto-filled statement CB for {len(filled)} month(s) of "
            f"{account.source_ac} from {uploaded.name}: {', '.join(filled)}.",
        )
    if not_found:
        messages.warning(
            request,
            "Could not find a closing balance for: " + ", ".join(not_found)
            + ". File is saved against these rows; enter the amount manually.",
        )
    if missing_row:
        messages.warning(
            request,
            "No summary row yet (run Build Month Summary first) for: "
            + ", ".join(missing_row),
        )
    if not filled and not not_found and not missing_row:
        messages.warning(request, f"Nothing to update for {account.source_ac} in this fiscal year.")

    return redirect(back_url)


def get_object_or_404_fiscal_year(fy_pk):
    from gl.fiscal_years.models import FiscalYear

    if fy_pk and str(fy_pk).isdigit():
        return FiscalYear.objects.filter(pk=int(fy_pk)).first()
    return None


@login_required
def bank_transactions_summary_update_cb(request):
    from urllib.parse import urlencode

    if request.method != "POST":
        return redirect("bank_transactions_summary_report")

    fy_pk = request.POST.get("fy", "")
    back_url = f"{reverse('bank_transactions_summary_report')}?{urlencode({'fy': fy_pk})}"

    row = get_object_or_404(BankTransactionSourceSummary, pk=request.POST.get("pk"))
    row.cb_from_statement = row.cb
    row.save(update_fields=["cb_from_statement"])
    messages.success(
        request,
        f"Statement CB set to {row.cb:,.2f} for {row.source_ac_id} {row.ym}.",
    )
    return redirect(back_url)


@login_required
def bank_transactions_summary_update_cb_annual(request):
    from urllib.parse import urlencode

    if request.method != "POST":
        return redirect("bank_transactions_summary_report")

    fy_pk = request.POST.get("fy", "")
    back_url = f"{reverse('bank_transactions_summary_report')}?{urlencode({'fy': fy_pk})}"

    fiscal_year = get_object_or_404_fiscal_year(fy_pk)
    if fiscal_year is None:
        messages.error(request, "Choose a fiscal year first.")
        return redirect(back_url)

    account = SourceBankCashAc.objects.filter(source_ac=request.POST.get("source_ac")).first()
    if account is None:
        messages.error(request, "Choose an account first.")
        return redirect(back_url)

    months = calendar_months_in_fiscal_year(fiscal_year)
    yms = [m["ym"] for m in months]

    rows = BankTransactionSourceSummary.objects.filter(source_ac=account, ym__in=yms)
    updated = 0
    for row in rows:
        row.cb_from_statement = row.cb
        row.save(update_fields=["cb_from_statement"])
        updated += 1

    if updated:
        messages.success(
            request,
            f"Statement CB set to CB for {updated} month(s) of {account.source_ac} in {fiscal_year.fy_no}.",
        )
    else:
        messages.warning(
            request,
            f"No summary rows found for {account.source_ac} in {fiscal_year.fy_no}. "
            "Run Build Month Summary first.",
        )
    return redirect(back_url)


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
def bank_transactions_source_accounts(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            ac = get_object_or_404(SourceBankCashAc, pk=request.POST.get("pk"))
            ac.delete()
            return redirect("bank_transactions_source_accounts")
        return redirect("bank_transactions_source_accounts")

    return render(
        request,
        "bank_transactions/bank_transactions_source_accounts.html",
        {"accounts": SourceBankCashAc.objects.all()},
    )


def _bank_transactions_source_account_form_view(request, instance=None):
    if request.method == "POST":
        form = SourceBankCashAcForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("bank_transactions_source_accounts")
    else:
        form = SourceBankCashAcForm(instance=instance)

    return render(
        request,
        "bank_transactions/bank_transactions_source_account_form.html",
        {"form": form, "account": instance},
    )


@login_required
def bank_transactions_source_account_create(request):
    return _bank_transactions_source_account_form_view(request)


@login_required
def bank_transactions_source_account_edit(request, pk):
    ac = get_object_or_404(SourceBankCashAc, pk=pk)
    return _bank_transactions_source_account_form_view(request, instance=ac)


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


