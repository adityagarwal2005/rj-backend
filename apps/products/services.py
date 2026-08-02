"""
Business logic for the products app. Kept separate from views/serializers so
other apps (orders) can reuse stock logic without importing view code.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.products.models import Product, Review


def visible_products_queryset(user):
    """Admins see every product; everyone else only sees active, in-catalog items."""
    queryset = Product.objects.select_related("category").prefetch_related("images")
    if user.is_authenticated and user.is_admin:
        return queryset
    return queryset.filter(is_active=True, category__is_active=True)


@transaction.atomic
def decrease_stock(product: Product, quantity: int) -> Product:
    """Locks the product row and decrements stock; used when an order is placed."""
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    if locked_product.stock_quantity < quantity:
        raise ValidationError(f"Only {locked_product.stock_quantity} unit(s) of '{locked_product.name}' left in stock.")
    locked_product.stock_quantity -= quantity
    locked_product.save(update_fields=["stock_quantity"])
    return locked_product


@transaction.atomic
def restore_stock(product: Product, quantity: int) -> Product:
    """Used when an order is cancelled/refunded."""
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    locked_product.stock_quantity += quantity
    locked_product.save(update_fields=["stock_quantity"])
    return locked_product


def create_review(user, product: Product, order_id, rating: int, comment: str) -> Review:
    """Only someone with a delivered order containing this product can review it - see apps.products.models.Review."""
    from apps.orders.models import Order, OrderStatus

    order = Order.objects.filter(id=order_id, user=user, status=OrderStatus.DELIVERED).first()
    if order is None:
        raise ValidationError("We couldn't find a delivered order matching that.")
    if not order.items.filter(product=product).exists():
        raise ValidationError("This product wasn't part of that order.")
    if Review.objects.filter(order=order, product=product).exists():
        raise ValidationError("You've already reviewed this product for that order.")
    return Review.objects.create(order=order, product=product, user=user, rating=rating, comment=comment)
