"""Business logic for cart management and checkout."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.notifications import services as notification_services
from apps.orders import referrals
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatus, OrderStatusHistory
from apps.orders.pricing import discount_for_code, is_known_code
from apps.products import services as product_services

# How long an unpaid order sits before we nudge the customer, and before we
# give up entirely and release its stock back to the catalog.
ABANDONED_REMINDER_DELAY = timedelta(hours=2)
STALE_ORDER_CANCEL_DELAY = timedelta(hours=48)


def record_status_change(order: Order) -> None:
    """Logs the order's *current* status as a timeline entry - call this right after any order.save() that changes status."""
    OrderStatusHistory.objects.create(order=order, status=order.status)


def get_or_create_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def add_item_to_cart(user, product, quantity: int) -> CartItem:
    cart = get_or_create_cart(user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
    if not created:
        item.quantity += quantity
        item.save(update_fields=["quantity"])
    return item


def update_cart_item_quantity(user, item_id: int, quantity: int) -> CartItem:
    item = CartItem.objects.select_related("cart").get(id=item_id, cart__user=user)
    item.quantity = quantity
    item.save(update_fields=["quantity"])
    return item


def remove_cart_item(user, item_id: int) -> None:
    CartItem.objects.filter(id=item_id, cart__user=user).delete()


def apply_promo_code(user, code: str) -> Cart:
    cart = get_or_create_cart(user)
    if not is_known_code(code):
        raise ValidationError("That code doesn't look right.")
    percentage, _ = discount_for_code(code, cart.subtotal_amount)
    if percentage == 0:
        raise ValidationError("Your order doesn't qualify for this code yet.")
    cart.applied_promo_code = code.strip().upper()
    cart.save(update_fields=["applied_promo_code"])
    return cart


def remove_promo_code(user) -> Cart:
    cart = get_or_create_cart(user)
    cart.applied_promo_code = ""
    cart.save(update_fields=["applied_promo_code"])
    return cart


@transaction.atomic
def create_order_from_cart(
    user, address=None, notes: str = "", is_gift: bool = False, gift_message: str = "",
) -> Order:
    """
    address=None is the WhatsApp checkout path: the order (and its stock
    reservation) is created immediately, but stays OrderStatus.AWAITING_DETAILS
    until a staff member fills in the address given in chat - see
    apps.orders.views.OrderViewSet.checkout_whatsapp.
    """
    cart = get_or_create_cart(user)
    cart_items = list(cart.items.select_related("product"))

    if not cart_items:
        raise ValidationError("Your cart is empty.")

    # Must be computed before the Order row below exists, or "is this their
    # first order" would immediately see the order we're about to create.
    is_first_order = referrals.is_first_order_for(user)
    referral_credit = referrals.available_credit_for(user)

    order = Order.objects.create(
        user=user,
        address=address,
        status=OrderStatus.PENDING if address is not None else OrderStatus.AWAITING_DETAILS,
        subtotal_amount=0,
        total_amount=0,
        notes=notes,
        is_gift=is_gift,
        gift_message=gift_message if is_gift else "",
    )
    record_status_change(order)
    subtotal_amount = Decimal("0")

    for cart_item in cart_items:
        product = cart_item.product
        product_services.decrease_stock(product, cart_item.quantity)

        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.effective_price,
            quantity=cart_item.quantity,
        )
        subtotal_amount += product.effective_price * cart_item.quantity

    discount_percentage, discount_amount = discount_for_code(cart.applied_promo_code, subtotal_amount)

    referral_discount_amount = referrals.referee_discount_for(user, is_first_order)
    if referral_credit is not None:
        referral_discount_amount += referral_credit.amount
        referral_credit.is_used = True
        referral_credit.used_on_order = order
        referral_credit.save(update_fields=["is_used", "used_on_order"])

    order.subtotal_amount = subtotal_amount
    order.discount_percentage = discount_percentage
    order.discount_amount = discount_amount
    order.referral_discount_amount = referral_discount_amount
    order.total_amount = subtotal_amount - discount_amount - referral_discount_amount
    # This business is prepaid-only for now, so an order set to PENDING isn't
    # confirmed until payment is manually verified (see apps.payments.signals,
    # which flips PENDING/AWAITING_DETAILS orders to CONFIRMED on payment success).
    order.save(update_fields=[
        "subtotal_amount", "discount_percentage", "discount_amount", "referral_discount_amount", "total_amount",
    ])

    cart_items_ids = [item.id for item in cart_items]
    CartItem.objects.filter(id__in=cart_items_ids).delete()
    if cart.applied_promo_code:
        cart.applied_promo_code = ""
        cart.save(update_fields=["applied_promo_code"])

    notification_services.notify_order_status_change(order)
    return order


@transaction.atomic
def cancel_order(order: Order) -> Order:
    if order.status == OrderStatus.CANCELLED:
        raise ValidationError("Order is already cancelled.")

    for item in order.items.select_related("product"):
        if item.product is not None:
            product_services.restore_stock(item.product, item.quantity)

    # A cancelled order shouldn't have permanently spent a referral credit.
    from apps.users.models import ReferralCredit

    ReferralCredit.objects.filter(used_on_order=order).update(is_used=False, used_on_order=None)

    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status"])
    record_status_change(order)
    notification_services.notify_order_status_change(order)
    return order


def send_abandoned_order_reminders() -> int:
    """Nudge customers with a real unpaid order sitting untouched for a while. Sends at most once per order."""
    cutoff = timezone.now() - ABANDONED_REMINDER_DELAY
    stale_orders = Order.objects.filter(
        status=OrderStatus.PENDING, created_at__lte=cutoff, abandoned_reminder_sent_at__isnull=True,
    ).select_related("user").prefetch_related("items")

    count = 0
    for order in stale_orders:
        notification_services.notify_abandoned_order(order)
        order.abandoned_reminder_sent_at = timezone.now()
        order.save(update_fields=["abandoned_reminder_sent_at"])
        count += 1
    return count


def auto_cancel_stale_pending_orders() -> int:
    """
    Give up on orders nobody ever paid for and release their stock -
    otherwise abandoned carts would quietly hold inventory hostage forever.
    """
    cutoff = timezone.now() - STALE_ORDER_CANCEL_DELAY
    stale_orders = Order.objects.filter(status=OrderStatus.PENDING, created_at__lte=cutoff)

    count = 0
    for order in stale_orders:
        cancel_order(order)
        count += 1
    return count
