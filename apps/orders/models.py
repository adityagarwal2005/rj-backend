from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.orders.pricing import calculate_discount
from apps.products.models import Product


class Address(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=12)
    country = models.CharField(max_length=100, default="India")
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.full_name} - {self.city}"


class Cart(TimeStampedModel):
    """Every user has exactly one running cart, created lazily on first use."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")

    def __str__(self):
        return f"Cart({self.user.email})"

    @property
    def subtotal_amount(self):
        return sum((item.subtotal for item in self.items.all()), start=Decimal("0"))

    @property
    def discount_percentage(self):
        return calculate_discount(self.subtotal_amount)[0]

    @property
    def discount_amount(self):
        return calculate_discount(self.subtotal_amount)[1]

    @property
    def total_amount(self):
        return self.subtotal_amount - self.discount_amount


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def subtotal(self):
        return self.product.effective_price * self.quantity


class OrderStatus(models.TextChoices):
    AWAITING_DETAILS = "awaiting_details", "Awaiting Details (WhatsApp)"
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class Order(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Uses a UUID primary key (not sequential) so order ids aren't guessable/
    enumerable and don't leak total order volume to customers.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    # Null while an order started via WhatsApp checkout is still awaiting the
    # customer's address, which is collected in chat instead of a form - see
    # OrderStatus.AWAITING_DETAILS and apps.orders.services.create_order_from_cart.
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="orders", null=True, blank=True)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self):
        return f"Order {self.id}"


class OrderItem(TimeStampedModel):
    """
    Snapshots product name/price at the time of purchase - the order must
    stay historically accurate even if the product is later renamed,
    repriced, or deleted from the catalog.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name="order_items")
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity
