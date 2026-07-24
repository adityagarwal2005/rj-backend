"""
Payment gateway integration point.

Each gateway implements the same PaymentGateway interface so swapping/adding
a provider (Razorpay, Stripe, etc.) later means writing one new class here
and registering it in GATEWAYS, with no changes to views/models/orders.
"""

import razorpay
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.payments.models import Payment, PaymentGatewayChoice, PaymentStatus


class PaymentGateway:
    """Interface every concrete gateway must implement."""

    code = None

    def create_payment_intent(self, payment: Payment) -> dict:
        """Called right after a Payment row is created. Returns data the
        frontend needs to complete payment (e.g. a gateway order id / checkout URL)."""
        raise NotImplementedError

    def verify_payment(self, payment: Payment, callback_payload: dict) -> bool:
        """Called from the gateway webhook/callback. Returns True if the
        payment is verified as successful."""
        raise NotImplementedError


def get_manual_payment_details() -> dict:
    """
    Static UPI/bank details shown to customers for prepaid manual transfer.
    Configured via env vars (see .env.example) rather than hardcoded, since
    these are real business details, not secrets.
    """
    return {
        "upi_id": settings.PAYMENT_UPI_ID,
        "bank_account_name": settings.PAYMENT_BANK_ACCOUNT_NAME,
        "whatsapp_number": settings.PAYMENT_WHATSAPP_NUMBER,
        "bank_account_number": settings.PAYMENT_BANK_ACCOUNT_NUMBER,
        "bank_ifsc": settings.PAYMENT_BANK_IFSC,
        "bank_name": settings.PAYMENT_BANK_NAME,
        "instructions": (
            "Please pay the order total via UPI using the details above, then we'll "
            "confirm your payment and start preparing your order."
        ),
        "razorpay_enabled": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
    }


class ManualGateway(PaymentGateway):
    """
    Early-stage prepaid flow: no payment API, just UPI/bank transfer. The
    order stays 'pending' until a human (you) confirms the transfer was
    received - see apps.payments.signals, which flips the order to
    'confirmed' automatically the moment this Payment's status is set to
    'success' (e.g. from the Django admin).
    """

    code = PaymentGatewayChoice.MANUAL

    def create_payment_intent(self, payment: Payment) -> dict:
        return {"gateway": self.code, "amount": str(payment.amount), **get_manual_payment_details()}

    def verify_payment(self, payment: Payment, callback_payload: dict) -> bool:
        # There is no automated callback for manual transfers - verification
        # happens by a staff member editing the Payment record directly.
        raise NotImplementedError("Manual payments are confirmed via the admin, not this endpoint.")


class CODGateway(PaymentGateway):
    """Not currently offered (business is prepaid-only for now) - kept for when COD returns."""

    code = PaymentGatewayChoice.COD

    def create_payment_intent(self, payment: Payment) -> dict:
        return {"gateway": self.code, "message": "Pay in cash when your order is delivered."}

    def verify_payment(self, payment: Payment, callback_payload: dict) -> bool:
        return True


def get_razorpay_client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


class RazorpayGateway(PaymentGateway):
    """
    Automated gateway: create_payment_intent opens a Razorpay Order that the
    frontend's Razorpay Checkout widget pays against; verify_payment checks
    the HMAC signature Razorpay's checkout callback returns to prove the
    payment actually succeeded (not just that the browser says so). Only
    registered in GATEWAYS below when real keys are configured.
    """

    code = PaymentGatewayChoice.RAZORPAY

    def create_payment_intent(self, payment: Payment) -> dict:
        client = get_razorpay_client()
        amount_paise = int(payment.amount * 100)
        razorpay_order = client.order.create(
            {
                "amount": amount_paise,
                "currency": payment.currency,
                "receipt": str(payment.id),
                "notes": {"order_id": str(payment.order_id)},
            }
        )
        payment.gateway_order_id = razorpay_order["id"]
        payment.save(update_fields=["gateway_order_id"])
        return {
            "gateway": self.code,
            "key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order["id"],
            "amount": amount_paise,
            "currency": payment.currency,
        }

    def verify_payment(self, payment: Payment, callback_payload: dict) -> bool:
        client = get_razorpay_client()
        try:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": payment.gateway_order_id,
                    "razorpay_payment_id": callback_payload.get("gateway_payment_id", ""),
                    "razorpay_signature": callback_payload.get("gateway_signature", ""),
                }
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False


def _active_gateways() -> dict:
    """
    Built fresh on each call (rather than a module-level dict) so that
    turning Razorpay on/off is purely a matter of the env vars being set -
    no restart-sensitive import-time caching, and tests can toggle it with
    override_settings.

    COD is intentionally left out: the business is prepaid-only right now,
    so only "manual" (and "razorpay", once configured) can be initiated via
    the API, even though the COD gateway class (and DB choice, for
    historical orders) still exists.
    """
    gateways = {PaymentGatewayChoice.MANUAL: ManualGateway()}
    if settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
        gateways[PaymentGatewayChoice.RAZORPAY] = RazorpayGateway()
    return gateways


def confirm_razorpay_order_payment(gateway_order_id: str, gateway_payment_id: str, succeeded: bool) -> Payment | None:
    """
    Used by the Razorpay dashboard webhook (server-to-server), which is a
    reliability safety net alongside the client-side checkout callback: if a
    customer's browser closes right after paying, before the checkout
    callback POSTs to confirm_payment() above, this still confirms the order.
    """
    payment = (
        Payment.objects.filter(gateway=PaymentGatewayChoice.RAZORPAY, gateway_order_id=gateway_order_id)
        .order_by("-created_at")
        .first()
    )
    if payment is None or payment.status != PaymentStatus.PENDING:
        return payment
    payment.status = PaymentStatus.SUCCESS if succeeded else PaymentStatus.FAILED
    payment.gateway_payment_id = gateway_payment_id
    payment.save(update_fields=["status", "gateway_payment_id"])
    return payment


def get_gateway(code: str) -> PaymentGateway:
    gateway = _active_gateways().get(code)
    if gateway is None:
        raise ValidationError(f"Unsupported payment gateway: {code}")
    return gateway


@transaction.atomic
def initiate_payment(order, gateway_code: str) -> tuple[Payment, dict]:
    gateway = get_gateway(gateway_code)
    payment = Payment.objects.create(order=order, gateway=gateway_code, amount=order.total_amount)
    intent_data = gateway.create_payment_intent(payment)
    return payment, intent_data


@transaction.atomic
def confirm_payment(payment: Payment, callback_payload: dict) -> Payment:
    gateway = get_gateway(payment.gateway)
    is_verified = gateway.verify_payment(payment, callback_payload)
    payment.status = PaymentStatus.SUCCESS if is_verified else PaymentStatus.FAILED
    payment.gateway_payment_id = callback_payload.get("gateway_payment_id", "")
    payment.gateway_signature = callback_payload.get("gateway_signature", "")
    payment.save(update_fields=["status", "gateway_payment_id", "gateway_signature"])
    return payment
