from django.db.models import Avg
from rest_framework import serializers

from apps.products.models import Category, Product, ProductImage, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "is_active"]
        read_only_fields = ["id", "slug"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "is_primary", "display_order"]
        read_only_fields = ["id"]


class ReviewStatsMixin:
    """
    Shared by List/Detail serializers so rating stats stay in sync everywhere a
    product appears. Reads the average_rating/review_count annotations added
    by apps.products.services.visible_products_queryset (one query for the
    whole page) instead of running a fresh aggregate per row here.
    """

    def get_average_rating(self, obj):
        average = getattr(obj, "average_rating", None)
        if average is None:
            average = obj.reviews.aggregate(value=Avg("rating"))["value"]
        return round(average, 1) if average is not None else None

    def get_review_count(self, obj):
        count = getattr(obj, "review_count", None)
        return count if count is not None else obj.reviews.count()


class WishlistStatusMixin:
    """
    Shared by List/Detail serializers. Reads a `wishlisted_product_ids` set
    the view puts in context (one query per page, see
    ProductViewSet.get_serializer_context) instead of querying per row.
    Always False for anonymous requests - context won't have the key set.
    """

    def get_is_wishlisted(self, obj):
        return obj.id in self.context.get("wishlisted_product_ids", set())


class ProductListSerializer(ReviewStatsMixin, WishlistStatusMixin, serializers.ModelSerializer):
    """Lightweight representation for catalog/listing pages."""

    category = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    secondary_image = serializers.SerializerMethodField()
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "category", "price", "discount_price",
            "effective_price", "bulk_price", "bulk_min_quantity", "weight_label", "stock_quantity", "in_stock",
            "is_featured", "primary_image", "secondary_image", "average_rating", "review_count", "is_wishlisted",
        ]

    def _ordered_images(self, obj):
        """Primary first, then the rest by display_order - the order a shopper should see them in."""
        images = sorted(obj.images.all(), key=lambda img: (not img.is_primary, img.display_order, img.id))
        return images

    def get_primary_image(self, obj):
        images = self._ordered_images(obj)
        return ProductImageSerializer(images[0]).data["image"] if images else None

    def get_secondary_image(self, obj):
        """
        The shot a catalog card cross-fades to on hover. Null for a product
        with only one photo, in which case the card just stays on the first.
        """
        images = self._ordered_images(obj)
        return ProductImageSerializer(images[1]).data["image"] if len(images) > 1 else None


class ProductDetailSerializer(ReviewStatsMixin, WishlistStatusMixin, serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True
    )
    images = ProductImageSerializer(many=True, read_only=True)
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "ingredients", "category", "category_id",
            "price", "discount_price", "effective_price", "bulk_price", "bulk_min_quantity", "weight_label",
            "stock_quantity", "in_stock", "is_active", "is_featured",
            "images", "average_rating", "review_count", "is_wishlisted", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "user_name", "rating", "comment", "created_at"]
        read_only_fields = fields


class CreateReviewSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
