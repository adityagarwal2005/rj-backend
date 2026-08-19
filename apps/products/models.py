from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel
from apps.core.storage import SupabaseMediaStorage


class Category(TimeStampedModel):
    """
    e.g. Ladoo, Barfi, Ghewar. Only one product exists today, but every
    product needs a category from day one so the catalog can grow without
    a schema change later.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(TimeStampedModel):
    """A single chocolate item, e.g. 'Kunafa Chocolate'."""

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    ingredients = models.TextField(
        blank=True, help_text="Comma-separated ingredient list, shown on the product detail page."
    )

    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    discount_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))]
    )

    # Per-unit price break for buying several at once (e.g. "buy 2, pay 110
    # each instead of 120") - distinct from discount_price above, which is a
    # flat sale price applied regardless of quantity. Both null by default;
    # see price_for_quantity() for how they combine.
    bulk_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))],
        help_text="Per-unit price once bulk_min_quantity is reached, e.g. 110.00.",
    )
    bulk_min_quantity = models.PositiveIntegerField(
        null=True, blank=True, default=2, help_text="Quantity at which bulk_price kicks in, e.g. 2.",
    )

    # Rajasthani sweets are typically sold by weight rather than by unit count.
    weight_label = models.CharField(max_length=50, help_text="e.g. 250g, 500g, 1kg", default="500g")
    stock_quantity = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "is_featured"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price is not None else self.price

    def price_for_quantity(self, quantity: int):
        """Per-unit price for buying `quantity` of this product - drops to bulk_price once bulk_min_quantity is met."""
        if self.bulk_price is not None and self.bulk_min_quantity and quantity >= self.bulk_min_quantity:
            return self.bulk_price
        return self.effective_price

    @property
    def in_stock(self):
        return self.stock_quantity > 0


def product_image_upload_path(instance, filename):
    return f"products/{instance.product_id}/{filename}"


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=product_image_upload_path, storage=SupabaseMediaStorage())
    alt_text = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return f"Image for {self.product.name}"


class Review(TimeStampedModel):
    """
    A rating/review tied to a specific delivered order - not a free-for-all
    review box, so every review on the site is from someone who actually
    received the product (see apps.products.services.create_review).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="one_review_per_order_product"),
        ]

    def __str__(self):
        return f"{self.rating}★ {self.product.name} by {self.user.email}"


class WishlistItem(TimeStampedModel):
    """A product a signed-in customer has saved for later - see apps.products.views.ProductViewSet.wishlist."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="one_wishlist_entry_per_user_product"),
        ]

    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"
