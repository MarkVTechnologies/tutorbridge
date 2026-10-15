"""Money helpers. All amounts are integer kobo; rounding is defined once, here."""


def percent_of(amount_kobo: int, pct) -> int:
    """Percentage of an amount, rounded half-up to the nearest kobo."""
    from decimal import ROUND_HALF_UP, Decimal

    value = (Decimal(amount_kobo) * Decimal(str(pct)) / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(value)


def split_commission(amount_kobo: int, commission_pct) -> tuple[int, int]:
    """Return (tutor_share, platform_share). Platform share is rounded; tutor gets the remainder so the sum is exact."""
    platform = percent_of(amount_kobo, commission_pct)
    return amount_kobo - platform, platform


def naira(amount_kobo: int) -> str:
    return f"₦{amount_kobo / 100:,.2f}"
