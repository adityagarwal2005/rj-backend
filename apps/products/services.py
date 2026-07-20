"""
Business logic for the products app. Kept separate from views/serializers so
other apps (orders) can reuse stock logic without importing view code.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.products.models import Product


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
