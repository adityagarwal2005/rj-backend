from rest_framework import serializers

from apps.orders.models import Order
from apps.payments.models import Payment, PaymentGatewayChoice


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "gateway", "status", "amount", "currency", "created_at"]
        read_only_fields = fields


class InitiatePaymentSerializer(serializers.Serializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", queryset=Order.objects.all())
    gateway = serializers.ChoiceField(choices=PaymentGatewayChoice.choices)

    def validate_order_id(self, order):
        request = self.context["request"]
        if order.user_id != request.user.id and not request.user.is_admin:
            raise serializers.ValidationError("This order does not belong to you.")
        return order


class PaymentCallbackSerializer(serializers.Serializer):
    gateway_payment_id = serializers.CharField(required=False, allow_blank=True)
    gateway_signature = serializers.CharField(required=False, allow_blank=True)
