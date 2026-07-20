from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.response import api_error, api_success
from apps.payments import services
from apps.payments.models import Payment
from apps.payments.serializers import (
    InitiatePaymentSerializer,
    PaymentCallbackSerializer,
    PaymentSerializer,
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
