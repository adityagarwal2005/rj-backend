from rest_framework import serializers

from apps.products.models import Category, Product, ProductImage


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


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight representation for catalog/listing pages."""

    category = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "category", "price", "discount_price",
            "effective_price", "weight_label", "stock_quantity", "in_stock",
            "is_featured", "primary_image",
        ]

    def get_primary_image(self, obj):
        image = next((img for img in obj.images.all() if img.is_primary), None) or next(
            iter(obj.images.all()), None
        )
        return ProductImageSerializer(image).data["image"] if image else None


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category", queryset=Category.objects.all(), write_only=True
    )
    images = ProductImageSerializer(many=True, read_only=True)
    effective_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "ingredients", "category", "category_id",
            "price", "discount_price", "effective_price", "weight_label",
            "stock_quantity", "in_stock", "is_active", "is_featured",
            "images", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]
