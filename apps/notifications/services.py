"""
Notification delivery. Every call here is synchronous today (dev uses the
console email backend). Both functions are written as plain module-level
functions with no request/view coupling specifically so that later they can
be wrapped with @shared_task (Celery) - callers wouldn't need to change, only
the `.delay(...)` call site would.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.notifications.models import Notification, NotificationType

logger = logging.getLogger("django")


def create_notification(user, title: str, message: str, notification_type: str = NotificationType.SYSTEM) -> Notification:
    return Notification.objects.create(user=user, title=title, message=message, type=notification_type)


def send_email(to_email: str, subject: str, message: str) -> bool:
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


def notify_order_status_change(order) -> None:
    title = f"Order {order.id} is now {order.get_status_display()}"
    message = f"Hi {order.user.full_name}, your RajwadiTukda order status changed to {order.get_status_display()}."
    create_notification(order.user, title, message, NotificationType.ORDER_UPDATE)
    send_email(order.user.email, title, message)


def notify_abandoned_order(order) -> None:
    items = ", ".join(f"{item.product_name} x {item.quantity}" for item in order.items.all())
    title = "You left something in your cart!"
    message = (
        f"Hi {order.user.full_name}, your order for {items} is still waiting on payment. "
        f"Complete it soon - unpaid orders are automatically released back to stock after 48 hours."
    )
    create_notification(order.user, title, message, NotificationType.PROMOTION)
    send_email(order.user.email, title, message)
