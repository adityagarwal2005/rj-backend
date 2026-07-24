from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.orders.models import Order


class PaymentGatewayChoice(models.TextChoices):
    MANUAL = "manual", "UPI / Bank Transfer"
    COD = "cod", "Cash on Delivery"  # kept for historical orders; not offered while prepaid-only
    RAZORPAY = "razorpay", "Razorpay"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Payment(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    One row per payment attempt against an order. Kept as its own app/table
    (rather than fields on Order) so a new gateway or a retried payment
    doesn't require touching the orders app at all.
    """

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20, choices=PaymentGatewayChoice.choices)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="INR")

    # Populated once the gateway responds; null for COD.
    gateway_order_id = models.CharField(max_length=100, blank=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    gateway_signature = models.CharField(max_length=255, blank=True)

    # Customer-submitted UPI transaction reference (UTR/RRN) for manual
    # transfers, so staff can match a bank-statement entry to this payment
    # instead of guessing from amount/timing alone.
    utr_reference = models.CharField(max_length=35, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.id} for Order {self.order_id}"
