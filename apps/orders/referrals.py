"""
Referral program: a friend's code gets the new customer money off their
first order, and rewards the referrer once that order is actually paid for.

Kept separate from apps.orders.pricing (which stays a pure, model-free tier
calculator) since this needs to query Order/ReferralCredit records tied to a
specific user - importing that here would create a circular import with
apps.orders.models, which pricing.py is deliberately kept free of.
"""

from decimal import Decimal

REFEREE_FIRST_ORDER_DISCOUNT = Decimal("30")
REFERRER_REWARD_AMOUNT = Decimal("30")


def is_first_order_for(user) -> bool:
    from apps.orders.models import Order

    return not Order.objects.filter(user=user).exists()


def referee_discount_for(user, is_first_order: bool) -> Decimal:
    """A one-time discount for someone who signed up via a referral code, on their first order only."""
    if user.referred_by_id is None or not is_first_order:
        return Decimal("0")
    return REFEREE_FIRST_ORDER_DISCOUNT


def available_credit_for(user):
    from apps.users.models import ReferralCredit

    return ReferralCredit.objects.filter(user=user, is_used=False).order_by("created_at").first()


def total_referral_discount_for(user) -> Decimal:
    """Best-effort preview total (e.g. for the live cart) - doesn't redeem anything."""
    credit = available_credit_for(user)
    discount = referee_discount_for(user, is_first_order_for(user))
    return discount + (credit.amount if credit else Decimal("0"))


def grant_referrer_reward_if_eligible(order) -> None:
    """
    Called once an order is confirmed (paid) - if this is the referred
    user's first confirmed order, the person who referred them earns a
    credit toward their own next order.
    """
    from apps.notifications import services as notification_services
    from apps.orders.models import Order, OrderStatus
    from apps.users.models import ReferralCredit

    user = order.user
    if user.referred_by_id is None or user.referral_reward_granted:
        return

    already_confirmed_before = (
        Order.objects.filter(user=user, status=OrderStatus.CONFIRMED).exclude(id=order.id).exists()
    )
    if already_confirmed_before:
        return

    ReferralCredit.objects.create(user=user.referred_by, amount=REFERRER_REWARD_AMOUNT)
    user.referral_reward_granted = True
    user.save(update_fields=["referral_reward_granted"])

    notification_services.create_notification(
        user.referred_by,
        "You earned a referral reward!",
        f"{user.full_name} placed their first order using your referral link - you've earned "
        f"₹{REFERRER_REWARD_AMOUNT} off your next order.",
    )
