"""Business logic for cart management and checkout."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.notifications import services as notification_services
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatus
from apps.orders.pricing import calculate_discount
from apps.products import services as product_services


def get_or_create_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def add_item_to_cart(user, product, quantity: int) -> CartItem:
    cart = get_or_create_cart(user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
    if not created:
        item.quantity += quantity
        item.save(update_fields=["quantity"])
    return item


def update_cart_item_quantity(user, item_id: int, quantity: int) -> CartItem:
    item = CartItem.objects.select_related("cart").get(id=item_id, cart__user=user)
    item.quantity = quantity
    item.save(update_fields=["quantity"])
    return item


def remove_cart_item(user, item_id: int) -> None:
    CartItem.objects.filter(id=item_id, cart__user=user).delete()


@transaction.atomic
def create_order_from_cart(user, address=None, notes: str = "") -> Order:
    """
    address=None is the WhatsApp checkout path: the order (and its stock
    reservation) is created immediately, but stays OrderStatus.AWAITING_DETAILS
    until a staff member fills in the address given in chat - see
    apps.orders.views.OrderViewSet.checkout_whatsapp.
    """
    cart = get_or_create_cart(user)
    cart_items = list(cart.items.select_related("product"))

    if not cart_items:
        raise ValidationError("Your cart is empty.")

    order = Order.objects.create(
        user=user,
        address=address,
        status=OrderStatus.PENDING if address is not None else OrderStatus.AWAITING_DETAILS,
        subtotal_amount=0,
        total_amount=0,
        notes=notes,
    )
    subtotal_amount = Decimal("0")

    for cart_item in cart_items:
        product = cart_item.product
        product_services.decrease_stock(product, cart_item.quantity)

        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.effective_price,
            quantity=cart_item.quantity,
        )
        subtotal_amount += product.effective_price * cart_item.quantity

    discount_percentage, discount_amount = calculate_discount(subtotal_amount)

    order.subtotal_amount = subtotal_amount
    order.discount_percentage = discount_percentage
    order.discount_amount = discount_amount
    order.total_amount = subtotal_amount - discount_amount
    # This business is prepaid-only for now, so an order set to PENDING isn't
    # confirmed until payment is manually verified (see apps.payments.signals,
    # which flips PENDING/AWAITING_DETAILS orders to CONFIRMED on payment success).
    order.save(update_fields=[
        "subtotal_amount", "discount_percentage", "discount_amount", "total_amount",
    ])

    cart_items_ids = [item.id for item in cart_items]
    CartItem.objects.filter(id__in=cart_items_ids).delete()

    notification_services.notify_order_status_change(order)
    return order


@transaction.atomic
def cancel_order(order: Order) -> Order:
    if order.status == OrderStatus.CANCELLED:
        raise ValidationError("Order is already cancelled.")

    for item in order.items.select_related("product"):
        if item.product is not None:
            product_services.restore_stock(item.product, item.quantity)

    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status"])
    notification_services.notify_order_status_change(order)
    return order
