"""
Confirms an order automatically the moment its payment is marked successful.

This is what makes the "prepaid, manually verified" flow work: a staff
member opens the Payment in Django admin, changes status to 'success' (after
checking the UPI/bank transfer arrived), hits save - and the order flips
to 'confirmed' and the customer gets notified, with no extra manual step.
This applies whether the order started on-site (status 'pending') or via
WhatsApp checkout (status 'awaiting_details' - fill in order.address first).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications import services as notification_services
from apps.orders import referrals
from apps.orders import services as order_services
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus


@receiver(post_save, sender=Payment)
def confirm_order_on_payment_success(sender, instance: Payment, **kwargs):
    if instance.status != PaymentStatus.SUCCESS:
        return

    # Always read the order fresh: `instance.order` can be an object cached
    # from before the order was cancelled (or otherwise changed), and acting
    # on that stale status would confirm an order that no longer exists.
    order = Order.objects.get(pk=instance.order_id)
    if order.status == OrderStatus.CANCELLED:
        # Money arrived for an order that no longer exists: most likely the
        # customer paid in their UPI app and closed the Razorpay sheet before
        # it saw the result, which abandons (cancels) the order - and then
        # Razorpay's webhook confirmed the capture. Nothing can safely
        # un-cancel it automatically (its stock has been released), so a
        # human has to either refund or re-create it. Silently returning here
        # left a customer charged with no order and nobody aware.
        notification_services.notify_admin_payment_for_cancelled_order(order, instance)
        return
    if order.status not in (OrderStatus.PENDING, OrderStatus.AWAITING_DETAILS):
        return

    order.status = OrderStatus.CONFIRMED
    order.save(update_fields=["status"])
    order_services.record_status_change(order)
    # The customer receipt and admin alert belong here, on real payment -
    # not at order creation, where they used to fire for payments that were
    # never completed. notify_order_placed_once is a no-op for COD and
    # WhatsApp orders, which already sent theirs at checkout.
    order_services.notify_order_placed_once(order)
    notification_services.notify_order_status_change(order)
    referrals.grant_referrer_reward_if_eligible(order)
