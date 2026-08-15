from config.views._std_imports import *  # noqa: F403

from .access import (
    _engagement_queryset_for_user,
    _has_module_access,
)
from .constants import MODULE_ENGAGEMENTS, MODULE_SETUP, MODULE_TOOLS

def gl_hub(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("You need Setup access to open the GL hub.")
    return render(request, "gl/gl_hub.html")


def _calendar_months_in_fiscal_year(fy):
    """Each calendar month overlapping ``fy`` as first-of-month date, last day, and label."""
    import calendar
    from datetime import date

    months = []
    cur = date(fy.start_date.year, fy.start_date.month, 1)
    while cur <= fy.end_date:
        last = calendar.monthrange(cur.year, cur.month)[1]
        pend = date(cur.year, cur.month, last)
        months.append(
            {
                "period_from": cur,
                "period_to": pend,
                "label": cur.strftime("%b %Y"),
            }
        )
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


@login_required
def gl_trial_balance(request):
    """GL trial balance: FY from GL rules, or ``tb_table_month`` for one month or YTD cumulative."""
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("You need Setup access to view the GL trial balance.")
    from decimal import Decimal

    from gl.fiscal_years.models import FiscalYear
    from gl.journal.models import TbTableMonth
    from gl.journal.trial_balance_report import build_gl_trial_balance_rows

    from config.models import ChartOfAccount

    today = timezone.localdate()
    fiscal_years = list(FiscalYear.objects.all().order_by("-fy_no"))
    current_fy = None
    for fy in fiscal_years:
        if fy.start_date <= today <= fy.end_date:
            current_fy = fy
            break

    fy_param = request.GET.get("fy")
    selected_fy = None
    if fy_param and str(fy_param).isdigit():
        selected_fy = FiscalYear.objects.filter(pk=int(fy_param)).first()
    if selected_fy is None:
        selected_fy = current_fy
    if selected_fy is None and fiscal_years:
        selected_fy = fiscal_years[0]

    month_param = (request.GET.get("month") or "").strip()
    selected_month_from = None
    month_label = ""
    if month_param and selected_fy is not None:
        parsed = parse_date(month_param)
        if parsed is not None:
            for m in _calendar_months_in_fiscal_year(selected_fy):
                if m["period_from"] == parsed:
                    selected_month_from = parsed
                    month_label = m["label"]
                    break

    month_options = (
        _calendar_months_in_fiscal_year(selected_fy) if selected_fy is not None else []
    )

    fy_months_json: dict[str, list[dict[str, str]]] = {}
    for fy in fiscal_years:
        fy_months_json[str(fy.pk)] = [
            {
                "value": m["period_from"].isoformat(),
                "label": (
                    f"{m['label']} ({m['period_from'].isoformat()} to {m['period_to'].isoformat()})"
                ),
            }
            for m in _calendar_months_in_fiscal_year(fy)
        ]

    submitted = request.GET.get("fy") is not None
    # YTD default on: absent param or last ytd=1 wins over hidden ytd=0 when checkbox checked.
    tb_month_ytd = request.GET.get("ytd") != "0"

    tb_rows: list[dict] = []
    total_dr = Decimal("0")
    total_cr = Decimal("0")
    balanced = True
    use_tb_table_month = False
    if submitted and selected_fy is not None:
        if selected_month_from is not None:
            use_tb_table_month = True
            first_m = selected_fy.start_date.replace(day=1)
            if tb_month_ytd:
                agg = (
                    TbTableMonth.objects.filter(
                        fiscal_year=selected_fy,
                        period_from__gte=first_m,
                        period_from__lte=selected_month_from,
                    )
                    .values("account_code")
                    .annotate(total=Sum("amount"))
                    .order_by("account_code")
                )
                codes = [row["account_code"] for row in agg]
            else:
                qs = (
                    TbTableMonth.objects.filter(
                        fiscal_year=selected_fy, period_from=selected_month_from
                    )
                    .order_by("account_code")
                )
                codes = list(qs.values_list("account_code", flat=True))
                agg = [{"account_code": r.account_code, "total": r.amount} for r in qs]
            name_by_code = {
                c.account_code: c.account_name.strip()
                for c in ChartOfAccount.objects.filter(account_code__in=codes)
            }
            for row in agg:
                amt = row["total"]
                if amt is None:
                    continue
                amt = Decimal(str(amt))
                if amt == 0:
                    continue
                if amt > 0:
                    dr, cr = amt, None
                    total_dr += amt
                else:
                    dr, cr = None, -amt
                    total_cr += -amt
                tb_rows.append(
                    {
                        "account_name": name_by_code.get(
                            row["account_code"], "Unmapped account"
                        ),
                        "account_code": row["account_code"],
                        "debit": dr,
                        "credit": cr,
                    }
                )
            balanced = abs(total_dr - total_cr) <= Decimal("0.01")
        else:
            tb_rows, total_dr, total_cr = build_gl_trial_balance_rows(selected_fy)
            balanced = abs(total_dr - total_cr) <= Decimal("0.01")

    return render(
        request,
        "gl/gl_trial_balance.html",
        {
            "fiscal_years": fiscal_years,
            "current_fy": current_fy,
            "selected_fy": selected_fy,
            "month_options": month_options,
            "selected_month_param": month_param if selected_month_from else "",
            "selected_month_from": selected_month_from,
            "month_label": month_label,
            "report_submitted": submitted,
            "tb_rows": tb_rows,
            "total_dr": total_dr,
            "total_cr": total_cr,
            "tb_balanced": balanced,
            "use_tb_table_month": use_tb_table_month,
            "tb_month_ytd": tb_month_ytd,
            "fy_months_json": fy_months_json,
        },
    )


@login_required
def sales_ledger_settings(request):
    if not _has_module_access(request.user, MODULE_SETUP):
        raise PermissionDenied("Admin only.")
    from config.models import SalesLedgerSettings

    instance = SalesLedgerSettings.get_solo()
    if request.method == "POST":
        form = SalesLedgerSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Sales ledger settings saved.")
            return redirect("sales_ledger_settings")
    else:
        form = SalesLedgerSettingsForm(instance=instance)
    return render(
        request,
        "setup/sales_ledger_settings.html",
        {"form": form},
    )


def setup_mail_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can edit mail settings.")

    from config.models import SmtpMailSettings

    instance = SmtpMailSettings.get_solo()
    if request.method == "POST":
        form = SmtpMailSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved settings.")
            return redirect("setup_mail_settings")
    else:
        form = SmtpMailSettingsForm(instance=instance)
    return render(
        request,
        "config/mail_settings.html",
        {"form": form},
    )


