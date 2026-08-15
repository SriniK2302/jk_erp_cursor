from decimal import Decimal

from engagements.models import Engagement


def _engagement_select_label(engagement: Engagement) -> str:
    """Human-readable label for engagement dropdowns (value is still engagement pk)."""
    name = engagement.client.display_name
    fy = engagement.fiscal_year.fy_no
    svc = engagement.service.service_desc
    return f"{name} · {fy} · {svc}"


def _format_fee_amount_display(value) -> str:
    if value is None or value == "":
        return ""
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return f"{int(d):,}"
    text = f"{d:,.2f}"
    if text.endswith(".00"):
        return text[:-3]
    return text.rstrip("0").rstrip(".")

