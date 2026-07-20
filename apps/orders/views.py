from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions import IsAdmin
from apps.core.response import api_error, api_success
from apps.notifications import services as notification_services
from apps.orders import services
from apps.orders.models import Address, CartItem, Order
from apps.orders.permissions import IsOrderOwnerOrAdmin
from apps.orders.serializers import (
    AddCartItemSerializer,
    AddressSerializer,
    CartSerializer,
    CreateOrderSerializer,
    CreateWhatsAppOrderSerializer,
    OrderSerializer,
    UpdateCartItemSerializer,
    UpdateOrderStatusSerializer,
)


class AddressViewSet(viewsets.ModelViewSet):
    """/api/orders/addresses/ - a user's own shipping addresses (admins see all)."""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_admin:
            return Address.objects.all()
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return api_success(self.get_serializer(instance).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return api_success(serializer.data, message="Address added successfully.", status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Address updated successfully.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_success(message="Address deleted successfully.")


class CartView(APIView):
    """GET /api/orders/cart/ - the authenticated user's current cart."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = services.get_or_create_cart(request.user)
        return api_success(CartSerializer(cart).data)


class CartItemListView(APIView):
    """POST /api/orders/cart/items/ - add a product to the cart."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.add_item_to_cart(
            request.user, serializer.validated_data["product"], serializer.validated_data["quantity"]
        )
        cart = item.cart
        return api_success(CartSerializer(cart).data, message="Item added to cart.", status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """PATCH/DELETE /api/orders/cart/items/{id}/ - update quantity or remove an item."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = services.update_cart_item_quantity(request.user, item_id, serializer.validated_data["quantity"])
        except CartItem.DoesNotExist:
            return api_error("Cart item not found.", status=status.HTTP_404_NOT_FOUND)
        return api_success(CartSerializer(item.cart).data, message="Cart updated successfully.")

    def delete(self, request, item_id):
        services.remove_cart_item(request.user, item_id)
        cart = services.get_or_create_cart(request.user)
        return api_success(CartSerializer(cart).data, message="Item removed from cart.")


class OrderViewSet(viewsets.ModelViewSet):
    """
    /api/orders/                GET (own orders / admin sees all), POST (checkout)
    /api/orders/{id}/           GET
    /api/orders/{id}/cancel/    POST - cancel and restock
    /api/orders/{id}/status/    PATCH - admin updates fulfillment status
    /api/orders/checkout-whatsapp/  POST - checkout without an address; given via WhatsApp chat instead
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsOrderOwnerOrAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if self.request.user.is_admin:
            return Order.objects.select_related("address").prefetch_related("items")
        return Order.objects.filter(user=self.request.user).select_related("address").prefetch_related("items")

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            order = services.create_order_from_cart(
                request.user,
                serializer.validated_data["address"],
                serializer.validated_data.get("notes", ""),
            )
        except DjangoValidationError as exc:
            return api_error(str(exc.message) if hasattr(exc, "message") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(OrderSerializer(order).data, message="Order placed successfully.", status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return api_success(self.get_serializer(instance).data)

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="checkout-whatsapp")
    def checkout_whatsapp(self, request):
        serializer = CreateWhatsAppOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = services.create_order_from_cart(
                request.user, notes=serializer.validated_data.get("notes", "")
            )
        except DjangoValidationError as exc:
            return api_error(str(exc.message) if hasattr(exc, "message") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(
            OrderSerializer(order).data,
            message="Order created - continue on WhatsApp to share your address and complete payment.",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            order = services.cancel_order(order)
        except DjangoValidationError as exc:
            return api_error(str(exc.message) if hasattr(exc, "message") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(OrderSerializer(order).data, message="Order cancelled successfully.")

    @action(detail=True, methods=["patch"], url_path="status", permission_classes=[IsAuthenticated, IsAdmin])
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = UpdateOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = serializer.validated_data["status"]
        order.save(update_fields=["status"])
        notification_services.notify_order_status_change(order)
        return api_success(OrderSerializer(order).data, message="Order status updated successfully.")
