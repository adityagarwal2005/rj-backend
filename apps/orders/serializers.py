from rest_framework import serializers

from apps.orders.models import Address, Cart, CartItem, Order, OrderItem
from apps.products.models import Product

# Early-stage business constraint: delivery is only available within Jaipur.
# Enforced here (not just in the frontend) so the restriction can't be
# bypassed by calling the API directly.
DELIVERABLE_CITY = "jaipur"


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id", "full_name", "phone", "line1", "line2", "city",
            "state", "postal_code", "country", "is_default",
        ]
        read_only_fields = ["id"]

    def validate_city(self, value):
        if value.strip().lower() != DELIVERABLE_CITY:
            raise serializers.ValidationError(
                "We currently deliver only within Jaipur. Support for other cities is coming soon!"
            )
        return value


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.DecimalField(source="product.effective_price", max_digits=8, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "subtotal"]
        read_only_fields = ["id"]


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(source="product", queryset=Product.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "subtotal_amount", "discount_percentage", "discount_amount", "total_amount"]


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # Null while a WhatsApp-checkout order is still awaiting its address - see
    # OrderStatus.AWAITING_DETAILS.
    address = AddressSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            "id", "status", "subtotal_amount", "discount_percentage", "discount_amount",
            "total_amount", "notes", "address", "items", "created_at",
        ]
        read_only_fields = [
            "id", "status", "subtotal_amount", "discount_percentage", "discount_amount",
            "total_amount", "items", "created_at",
        ]


class CreateOrderSerializer(serializers.Serializer):
    address_id = serializers.PrimaryKeyRelatedField(source="address", queryset=Address.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_address_id(self, address):
        request = self.context["request"]
        if address.user_id != request.user.id:
            raise serializers.ValidationError("This address does not belong to you.")
        return address


class CreateWhatsAppOrderSerializer(serializers.Serializer):
    """No address - the customer gives it to us in the WhatsApp chat instead."""

    notes = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order._meta.get_field("status").choices)
