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
from apps.orders.models import OrderStatus
from apps.payments.models import Payment, PaymentStatus


@receiver(post_save, sender=Payment)
def confirm_order_on_payment_success(sender, instance: Payment, **kwargs):
    if instance.status != PaymentStatus.SUCCESS:
        return

    order = instance.order
    if order.status not in (OrderStatus.PENDING, OrderStatus.AWAITING_DETAILS):
        return

    order.status = OrderStatus.CONFIRMED
    order.save(update_fields=["status"])
    notification_services.notify_order_status_change(order)
