from django.contrib import admin

from apps.orders.models import Address, Cart, CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total_amount", "created_at"]
    list_filter = ["status"]
    search_fields = ["id", "user__email"]
    inlines = [OrderItemInline]


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "city", "state", "is_default"]
    search_fields = ["full_name", "user__email", "city"]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at"]
    inlines = [CartItemInline]
