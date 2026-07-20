"""
Payment gateway integration point.

Each gateway implements the same PaymentGateway interface so swapping/adding
a provider (Razorpay, Stripe, etc.) later means writing one new class here
and registering it in GATEWAYS, with no changes to views/models/orders.
"""

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


class RazorpayGateway(PaymentGateway):
    """
    Not yet implemented - stubbed so the API contract (endpoints, request/
    response shapes) is stable for the frontend before a real Razorpay
    integration is added. Wiring this up later is just filling in these
    two methods with the `razorpay` SDK calls.
    """

    code = PaymentGatewayChoice.RAZORPAY

    def create_payment_intent(self, payment: Payment) -> dict:
        raise NotImplementedError("Razorpay integration is not implemented yet.")

    def verify_payment(self, payment: Payment, callback_payload: dict) -> bool:
        raise NotImplementedError("Razorpay integration is not implemented yet.")


# COD and Razorpay are intentionally left out of the active registry: the
# business is prepaid-only right now, so only "manual" can be initiated via
# the API even though the gateway classes (and DB choice, for historical
# orders) still exist.
GATEWAYS = {
    PaymentGatewayChoice.MANUAL: ManualGateway(),
}


def get_gateway(code: str) -> PaymentGateway:
    gateway = GATEWAYS.get(code)
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
