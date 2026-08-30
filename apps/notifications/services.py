"""
Notification delivery. Every call here is synchronous today. Both functions
are written as plain module-level functions with no request/view coupling
specifically so that later they can be wrapped with @shared_task (Celery) -
callers wouldn't need to change, only the `.delay(...)` call site would.

Emails go out as multipart HTML with a plain-text alternative. The text part
is not a formality: some clients (and most screen readers reading a raw
message) show it instead of the HTML, and a mail with no text part scores
worse with spam filters.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.notifications.models import Notification, NotificationType

logger = logging.getLogger("django")

# Hosted PNG rather than the site's SVG favicon: Gmail and Outlook don't
# render SVG in email at all.
EMAIL_LOGO_URL = (
    "https://eobrrlghxiuyfxyrumdv.supabase.co/storage/v1/object/public/rajwaditukda/branding/email-logo.png"
)

OTP_EXPIRY_MINUTES = 10
PASSWORD_RESET_EXPIRY_MINUTES = 30


def create_notification(user, title: str, message: str, notification_type: str = NotificationType.SYSTEM) -> Notification:
    return Notification.objects.create(user=user, title=title, message=message, type=notification_type)


def send_email(to_email: str, subject: str, message: str, template: str | None = None, context: dict | None = None) -> bool:
    """
    Send an email, as multipart HTML when a template is given.

    `message` is always the plain-text body and is never optional - it is the
    fallback part, and the only thing a client that refuses HTML will show.
    """
    try:
        email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])
        if template:
            html = render_to_string(
                template,
                {
                    "subject": subject,
                    "logo_url": EMAIL_LOGO_URL,
                    "site_url": settings.FRONTEND_URL,
                    **(context or {}),
                },
            )
            email.attach_alternative(html, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


def _order_url(order) -> str:
    return f"{settings.FRONTEND_URL}/orders/{order.id}"


def notify_order_status_change(order) -> None:
    status_label = order.get_status_display()
    title = f"Your order is now {status_label}"
    message = (
        f"Hi {order.user.full_name}, your RajwadiTukda order is now {status_label}.\n\n"
        f"Order ID: {order.id}\n"
        f"Track it here: {_order_url(order)}"
    )
    create_notification(order.user, title, message, NotificationType.ORDER_UPDATE)
    send_email(
        order.user.email,
        title,
        message,
        template="emails/order_status.html",
        context={
            "heading": f"Order {status_label.lower()}",
            "preheader": f"Your RajwadiTukda order is now {status_label}.",
            "first_name": order.user.full_name.split(" ")[0],
            "status_label": status_label,
            "order": order,
            "order_url": _order_url(order),
        },
    )


def notify_order_placed(order) -> None:
    """
    The customer's itemised receipt.

    Sent when the order is actually paid for (or placed via COD/WhatsApp,
    which have no upfront payment) - not at order creation, where it used to
    fire for payments the customer opened and then abandoned. See
    apps.orders.services.notify_order_placed_once.
    """
    items = list(order.items.all())
    item_lines = "\n".join(f"- {item.product_name} x {item.quantity} - ₹{item.subtotal}" for item in items)
    is_whatsapp = order.status == "awaiting_details"

    if is_whatsapp:
        next_steps = "We'll follow up on WhatsApp shortly to confirm your delivery address and payment."
    else:
        next_steps = "We're getting your chocolate ready. You can track your order anytime from your account."

    title = f"Thanks for your order, {order.user.full_name}!"
    message = (
        f"Hi {order.user.full_name}, thank you for ordering from RajwadiTukda!\n\n"
        f"Order ID: {order.id}\n"
        f"Items:\n{item_lines}\n"
        f"Total: ₹{order.total_amount}\n\n"
        f"{next_steps}"
    )
    create_notification(order.user, title, message, NotificationType.ORDER_UPDATE)
    send_email(
        order.user.email,
        title,
        message,
        template="emails/order_placed.html",
        context={
            "heading": "Thanks for your order!",
            "preheader": f"Order confirmed — ₹{order.total_amount}. We're getting it ready.",
            "first_name": order.user.full_name.split(" ")[0],
            "items": items,
            "order": order,
            "next_steps": next_steps,
            "order_url": _order_url(order),
        },
    )


def notify_admin_new_order(order) -> None:
    """
    The only place an order landing actually reaches a human proactively -
    everything else only notifies the customer. Silently does nothing if
    ADMIN_EMAIL isn't set, so this is a no-op in any environment that hasn't
    configured it.
    """
    if not settings.ADMIN_EMAIL:
        return

    is_whatsapp = order.status == "awaiting_details"
    short_channel = "WhatsApp" if is_whatsapp else "website"
    long_channel = "WhatsApp (address pending)" if is_whatsapp else "the website"
    items = list(order.items.all())
    item_lines = "\n".join(f"- {item.product_name} x {item.quantity}" for item in items)

    title = f"New order via {short_channel} - ₹{order.total_amount}"
    message = (
        f"New order placed via {long_channel}.\n\n"
        f"Customer: {order.user.full_name} ({order.user.email})\n"
        f"Items:\n{item_lines}\n"
        f"Total: ₹{order.total_amount}\n\n"
        "Open the admin dashboard to view and confirm it."
    )
    send_email(
        settings.ADMIN_EMAIL,
        title,
        message,
        template="emails/admin_new_order.html",
        context={
            "heading": f"New order — ₹{order.total_amount}",
            "preheader": f"{order.user.full_name} ordered via {short_channel}.",
            "subheading": "This order is paid for and ready to prepare." if not is_whatsapp else None,
            "order": order,
            "items": items,
            "address": order.address,
            "long_channel": long_channel,
        },
    )


def send_otp_email(user, code: str, purpose: str) -> None:
    if purpose == "signup":
        title = "Verify your email - RajwadiTukda"
        heading = "Verify your email"
        intro = "Welcome to RajwadiTukda! Use this code to verify your email and activate your account:"
    else:
        title = "Your login code - RajwadiTukda"
        heading = "Your login code"
        intro = "Use this code to log in to RajwadiTukda:"

    message = (
        f"Hi {user.full_name},\n\n{intro}\n\n{code}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email."
    )
    send_email(
        user.email,
        title,
        message,
        template="emails/otp_code.html",
        context={
            "heading": heading,
            "preheader": f"Your code is {code}. It expires in {OTP_EXPIRY_MINUTES} minutes.",
            "intro": intro,
            "code": code,
            "expiry_minutes": OTP_EXPIRY_MINUTES,
        },
    )


def send_password_reset_email(user, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={user.pk}&token={token}"
    title = "Reset your RajwadiTukda password"
    message = (
        f"Hi {user.full_name},\n\n"
        "Someone requested a password reset for your RajwadiTukda account. Open the link below to set a "
        f"new password (expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes):\n\n{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email - your password won't change."
    )
    send_email(
        user.email,
        title,
        message,
        template="emails/password_reset.html",
        context={
            "heading": "Reset your password",
            "preheader": f"Set a new password. The link expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes.",
            "reset_url": reset_url,
            "expiry_minutes": PASSWORD_RESET_EXPIRY_MINUTES,
        },
    )


def notify_abandoned_order(order) -> None:
    items = list(order.items.all())
    item_text = ", ".join(f"{item.product_name} x {item.quantity}" for item in items)
    title = "You left something in your cart!"
    message = (
        f"Hi {order.user.full_name}, your order for {item_text} is still waiting on payment. "
        "Complete it soon - unpaid orders are automatically released back to stock after 48 hours.\n\n"
        f"{_order_url(order)}"
    )
    create_notification(order.user, title, message, NotificationType.PROMOTION)
    send_email(
        order.user.email,
        title,
        message,
        template="emails/abandoned_order.html",
        context={
            "heading": "Still thinking it over?",
            "preheader": "Your order is waiting on payment.",
            "first_name": order.user.full_name.split(" ")[0],
            "items": items,
            "order": order,
            "order_url": _order_url(order),
        },
    )
