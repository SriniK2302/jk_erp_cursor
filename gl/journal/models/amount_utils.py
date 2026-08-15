from decimal import ROUND_HALF_UP, Decimal

_TWO_DP = Decimal("0.01")


def gl_amount_rounded(value) -> Decimal:
    """Money to 2 decimal places (half-up), for GL line amounts."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(_TWO_DP, rounding=ROUND_HALF_UP)
