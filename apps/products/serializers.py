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
    """Shared by List/Detail serializers so rating stats stay in sync everywhere a product appears."""

    def get_average_rating(self, obj):
        average = obj.reviews.aggregate(value=Avg("rating"))["value"]
        return round(average, 1) if average is not None else None

    def get_review_count(self, obj):
        return obj.reviews.count()


class ProductListSerializer(ReviewStatsMixin, serializers.ModelSerializer):
    """Lightweight representation for catalog/listing pages."""

    category = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "category", "price", "discount_price",
            "effective_price", "weight_label", "stock_quantity", "in_stock",
            "is_featured", "primary_image", "average_rating", "review_count",
        ]

    def get_primary_image(self, obj):
        image = next((img for img in obj.images.all() if img.is_primary), None) or next(
            iter(obj.images.all()), None
        )
        return ProductImageSerializer(image).data["image"] if image else None


class ProductDetailSerializer(ReviewStatsMixin, serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True
    )
    images = ProductImageSerializer(many=True, read_only=True)
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "ingredients", "category", "category_id",
            "price", "discount_price", "effective_price", "weight_label",
            "stock_quantity", "in_stock", "is_active", "is_featured",
            "images", "average_rating", "review_count", "created_at", "updated_at",
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
