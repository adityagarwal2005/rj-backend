from django.contrib import admin

from apps.orders.models import Address, Cart, CartItem, Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "created_at"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "status", "total_amount", "referral_discount_amount",
        "is_gift", "abandoned_reminder_sent_at", "created_at",
    ]
    list_filter = ["status", "is_gift"]
    search_fields = ["id", "user__email"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "city", "state", "is_default"]
    search_fields = ["full_name", "user__email", "city"]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "applied_promo_code", "created_at"]
    inlines = [CartItemInline]
