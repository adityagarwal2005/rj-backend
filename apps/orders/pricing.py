"""
Automatic bulk-order discount.

Kept as a pure, model-free module (no imports from apps.orders.models) so
both Cart (live preview) and Order (frozen at checkout) can share the exact
same calculation without a circular import between models.py and services.py.

No promo codes - the discount is automatic once a cart/order crosses the
threshold, nothing for a customer to type or a staff member to hand out.
"""

from decimal import ROUND_HALF_UP, Decimal

BULK_DISCOUNT_THRESHOLD = Decimal("800")
BULK_DISCOUNT_PERCENTAGE = Decimal("5")


def bulk_discount_for_subtotal(subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """Returns (discount_percentage, discount_amount) - zero if subtotal hasn't crossed the threshold."""
    if subtotal < BULK_DISCOUNT_THRESHOLD:
        return Decimal("0"), Decimal("0")
    amount = (subtotal * BULK_DISCOUNT_PERCENTAGE / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return BULK_DISCOUNT_PERCENTAGE, amount
