"""
Referral program: a friend's code gets the new customer money off their
first order, and rewards the referrer once that order is actually paid for.

Kept separate from apps.orders.pricing (which stays a pure, model-free tier
calculator) since this needs to query Order/ReferralCredit records tied to a
specific user - importing that here would create a circular import with
apps.orders.models, which pricing.py is deliberately kept free of.
"""

from decimal import Decimal

from django.db import transaction

REFEREE_FIRST_ORDER_DISCOUNT = Decimal("30")
REFERRER_REWARD_AMOUNT = Decimal("30")

# Minimum order subtotal before any referral benefit applies.
#
# Without this the programme paid out more than an order was worth, and was
# trivially farmable: sign up a second account with your own code, buy a ₹40
# lollipop for ₹10 (₹30 referee discount), and once it is paid the first
# account earns a ₹30 credit. Net result - the attacker is up a product and
# ₹20 of credit for ₹10 spent, repeatable for as long as they can supply
# fresh email addresses, and we also absorb the delivery cost each time.
#
# Set comfortably above the ₹30 payout so a referral always accompanies a
# genuinely profitable order. Tune to taste; the guard, not the exact
# number, is the important part.
REFERRAL_MIN_ORDER_SUBTOTAL = Decimal("300")


def is_first_order_for(user) -> bool:
    from apps.orders.models import Order

    return not Order.objects.filter(user=user).exists()


def meets_referral_minimum(subtotal: Decimal) -> bool:
    return subtotal >= REFERRAL_MIN_ORDER_SUBTOTAL


def referee_discount_for(user, is_first_order: bool, subtotal: Decimal) -> Decimal:
    """
    A one-time discount for someone who signed up via a referral code, on
    their first order only, and only once the order clears
    REFERRAL_MIN_ORDER_SUBTOTAL.
    """
    if user.referred_by_id is None or not is_first_order:
        return Decimal("0")
    if not meets_referral_minimum(subtotal):
        return Decimal("0")
    return REFEREE_FIRST_ORDER_DISCOUNT


def available_credit_for(user, for_update: bool = False):
    from apps.users.models import ReferralCredit

    queryset = ReferralCredit.objects.filter(user=user, is_used=False).order_by("created_at")
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def total_referral_discount_for(user, subtotal: Decimal) -> Decimal:
    """
    Preview total for the live cart - doesn't redeem anything.

    Takes the subtotal so it applies exactly the same minimum checkout does.
    Without it the cart promised a discount the order then wouldn't honour:
    a ₹40 cart displayed "₹10 to pay" and was charged ₹40.
    """
    if not meets_referral_minimum(subtotal):
        return Decimal("0")
    credit = available_credit_for(user)
    discount = referee_discount_for(user, is_first_order_for(user), subtotal)
    return discount + (credit.amount if credit else Decimal("0"))


def grant_referrer_reward_if_eligible(order) -> None:
    """
    Called once an order is confirmed (paid) - if this is the referred
    user's first confirmed order, the person who referred them earns a
    credit toward their own next order.
    """
    from apps.notifications import services as notification_services
    from apps.orders.models import Order, OrderStatus
    from apps.users.models import ReferralCredit, User

    # This runs from the Payment post_save signal, which can fire from a
    # plain (non-atomic) admin save as well as from confirm_payment/
    # confirm_razorpay_order_payment - wrap in our own atomic block so the
    # row lock below is always valid, and always closes the same window: two
    # near-simultaneous payment confirmations (client callback racing the
    # gateway webhook, or two separate orders for the same referred user)
    # could otherwise both reach here with referral_reward_granted still
    # False and both grant the reward.
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=order.user_id)
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
