"""
Promotional discount codes for early-stage launch pricing.

Kept as a pure, model-free module (no imports from apps.orders.models) so
both Cart (live preview) and Order (frozen at checkout) can share the exact
same calculation without a circular import between models.py and services.py.

Discounts are code-gated (not automatic) - a customer types SAVE10/SAVE20
at the cart and watches the price actually drop, rather than the discount
just silently already being there. Only two codes exist: at a flat ~200/bar
price, a customer can only ever land on exactly 200 (1 bar) or 400 (2 bars)
with whole units, so a middle "SAVE15 at 300" code would be unredeemable.
"""

from decimal import ROUND_HALF_UP, Decimal

PROMO_CODES: dict[str, tuple[Decimal, Decimal]] = {
    "SAVE10": (Decimal("200"), Decimal("10")),
    "SAVE20": (Decimal("400"), Decimal("20")),
}


def is_known_code(code: str) -> bool:
    return bool(code) and code.strip().upper() in PROMO_CODES


def discount_for_code(code: str, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """Returns (discount_percentage, discount_amount) - zero if the code is unknown or not yet earned."""
    if not code:
        return Decimal("0"), Decimal("0")
    tier = PROMO_CODES.get(code.strip().upper())
    if tier is None or subtotal < tier[0]:
        return Decimal("0"), Decimal("0")
    percentage = tier[1]
    amount = (subtotal * percentage / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return percentage, amount
