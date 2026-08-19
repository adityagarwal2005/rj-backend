from rest_framework import serializers

from apps.orders import referrals
from apps.orders.models import Address, Cart, CartItem, Order, OrderItem, OrderStatusHistory
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
    # Quantity-aware (not just product.effective_price) - a bulk price break
    # means the per-unit price itself can change as quantity changes, so
    # this has to be computed per row rather than read straight off Product.
    unit_price = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    # So the cart UI can cap +/- at what's actually in stock instead of only
    # discovering a shortfall at checkout - see apps.products.services.decrease_stock.
    stock_quantity = serializers.IntegerField(source="product.stock_quantity", read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "subtotal", "stock_quantity"]
        read_only_fields = ["id"]

    def get_unit_price(self, obj):
        return str(obj.product.price_for_quantity(obj.quantity))


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
    referral_discount_amount = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id", "items", "subtotal_amount", "discount_percentage", "discount_amount",
            "referral_discount_amount", "total_amount",
        ]

    def get_referral_discount_amount(self, obj):
        return referrals.total_referral_discount_for(obj.user)

    def get_total_amount(self, obj):
        return obj.total_amount - self.get_referral_discount_amount(obj)


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    product_slug = serializers.SlugField(source="product.slug", read_only=True, default=None)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "product_slug", "unit_price", "quantity", "subtotal"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["status", "created_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    # Null while a WhatsApp-checkout order is still awaiting its address - see
    # OrderStatus.AWAITING_DETAILS.
    address = AddressSerializer(read_only=True, allow_null=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    reviewed_product_ids = serializers.SerializerMethodField()
    payment_gateway = serializers.SerializerMethodField()
    payment_amount_due = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "status", "subtotal_amount", "discount_percentage", "discount_amount",
            "referral_discount_amount", "total_amount", "notes", "is_gift", "gift_message",
            "address", "items", "status_history", "reviewed_product_ids",
            "payment_gateway", "payment_amount_due", "created_at",
        ]
        read_only_fields = [
            "id", "status", "subtotal_amount", "discount_percentage", "discount_amount",
            "referral_discount_amount", "total_amount", "items", "status_history",
            "reviewed_product_ids", "payment_gateway", "payment_amount_due", "created_at",
        ]

    def get_reviewed_product_ids(self, obj):
        return list(obj.reviews.values_list("product_id", flat=True))

    def _latest_payment(self, obj):
        # Cached per-instance since both method fields below need it and
        # DRF calls each SerializerMethodField separately.
        if not hasattr(obj, "_latest_payment_cache"):
            obj._latest_payment_cache = obj.payments.order_by("-created_at").first()
        return obj._latest_payment_cache

    def get_payment_gateway(self, obj):
        payment = self._latest_payment(obj)
        return payment.gateway if payment else None

    def get_payment_amount_due(self, obj):
        payment = self._latest_payment(obj)
        return str(payment.amount) if payment else None


class CreateOrderSerializer(serializers.Serializer):
    address_id = serializers.PrimaryKeyRelatedField(source="address", queryset=Address.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    is_gift = serializers.BooleanField(required=False, default=False)
    gift_message = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)

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
