import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.response import api_error, api_success
from apps.payments import services
from apps.payments.models import Payment, PaymentGatewayChoice, PaymentStatus
from apps.payments.serializers import (
    InitiatePaymentSerializer,
    PaymentCallbackSerializer,
    PaymentSerializer,
    SubmitUtrSerializer,
)


class PaymentDetailsInfoView(APIView):
    """
    GET /api/payments/details/ - the static UPI/bank details customers pay
    to. Public since it's needed before/without an order (e.g. to show on a
    payment page) and carries no secrets, just business payment info.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return api_success(services.get_manual_payment_details())


class InitiatePaymentView(APIView):
    """POST /api/payments/initiate/ - start a payment attempt for an order."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            payment, intent_data = services.initiate_payment(
                serializer.validated_data["order"], serializer.validated_data["gateway"]
            )
        except (DjangoValidationError, NotImplementedError) as exc:
            return api_error(str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(
            {"payment": PaymentSerializer(payment).data, "gateway_data": intent_data},
            message="Payment initiated.",
            status=status.HTTP_201_CREATED,
        )


class SubmitPaymentUtrView(APIView):
    """
    POST /api/payments/utr/ - customer records the UPI transaction reference
    (UTR/RRN) for their most recent pending manual payment, so staff can
    match it against the bank statement instead of guessing from amount and
    timing alone.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubmitUtrSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        payment = (
            Payment.objects.filter(order=order, gateway=PaymentGatewayChoice.MANUAL, status=PaymentStatus.PENDING)
            .order_by("-created_at")
            .first()
        )
        if payment is None:
            return api_error("No pending payment found for this order.", status=status.HTTP_404_NOT_FOUND)
        payment.utr_reference = serializer.validated_data["utr_reference"]
        payment.save(update_fields=["utr_reference"])
        return api_success(PaymentSerializer(payment).data, message="Thanks! We'll verify your payment shortly.")


class PaymentDetailView(generics.RetrieveAPIView):
    """GET /api/payments/{id}/ - check a payment's status."""

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        if self.request.user.is_admin:
            return Payment.objects.all()
        return Payment.objects.filter(order__user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        return api_success(self.get_serializer(self.get_object()).data)


class PaymentWebhookView(APIView):
    """
    POST /api/payments/{id}/webhook/ - gateway calls this to confirm payment.
    AllowAny because gateways call it server-to-server, not as a logged-in
    user; real signature verification happens inside the gateway's
    verify_payment() implementation.
    """

    permission_classes = [AllowAny]

    def post(self, request, id):
        try:
            payment = Payment.objects.get(id=id)
        except Payment.DoesNotExist:
            return api_error("Payment not found.", status=status.HTTP_404_NOT_FOUND)

        serializer = PaymentCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = services.confirm_payment(payment, serializer.validated_data)
        except NotImplementedError as exc:
            return api_error(str(exc), status=status.HTTP_501_NOT_IMPLEMENTED)
        return api_success(PaymentSerializer(payment).data, message="Payment status updated.")


class RazorpayServerWebhookView(APIView):
    """
    POST /api/payments/razorpay/webhook/ - configured directly in the
    Razorpay Dashboard as a server-to-server safety net alongside the
    client-side checkout callback (PaymentWebhookView above): if a
    customer's browser closes right after paying, before that callback
    fires, this still confirms the order once Razorpay reports the capture.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
        if not settings.RAZORPAY_WEBHOOK_SECRET or not hmac.compare_digest(signature, expected):
            return api_error("Invalid signature.", status=status.HTTP_400_BAD_REQUEST)

        event = json.loads(request.body)
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        gateway_order_id = payment_entity.get("order_id", "")
        gateway_payment_id = payment_entity.get("id", "")
        event_name = event.get("event", "")

        if gateway_order_id and event_name in ("payment.captured", "payment.failed"):
            services.confirm_razorpay_order_payment(
                gateway_order_id, gateway_payment_id, succeeded=event_name == "payment.captured"
            )
        return api_success({}, message="ok")
