from django.contrib import admin

from apps.products.models import Category, Product, ProductImage, Review, WishlistItem


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "created_at"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name", "category", "price", "discount_price", "bulk_price", "bulk_min_quantity",
        "stock_quantity", "is_active", "is_featured",
    ]
    list_filter = ["category", "is_active", "is_featured"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "order", "created_at"]
    list_filter = ["rating"]
    search_fields = ["product__name", "user__email"]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
    search_fields = ["user__email", "product__name"]
