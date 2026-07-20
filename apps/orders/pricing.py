"""
Promotional discount tiers for early-stage launch pricing.

Kept as a pure, model-free module (no imports from apps.orders.models) so
both Cart (live preview) and Order (frozen at checkout) can share the exact
same calculation without a circular import between models.py and services.py.
"""

from decimal import ROUND_HALF_UP, Decimal

# Ordered highest-threshold-first; the first matching tier wins (flat
# percentage off the whole subtotal, not incremental/stacked).
DISCOUNT_TIERS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("400"), Decimal("20")),
    (Decimal("300"), Decimal("15")),
    (Decimal("200"), Decimal("10")),
)


def discount_percentage_for(subtotal: Decimal) -> Decimal:
    for threshold, percentage in DISCOUNT_TIERS:
        if subtotal >= threshold:
            return percentage
    return Decimal("0")


def calculate_discount(subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """Returns (discount_percentage, discount_amount) for a given subtotal."""
    percentage = discount_percentage_for(subtotal)
    amount = (subtotal * percentage / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return percentage, amount
