from django.contrib import admin

from apps.orders.models import Address, Cart, CartItem, Order, OrderItem, OrderStatus, OrderStatusHistory
from apps.orders.services import record_status_change


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "created_at"]
    can_delete = False


def _make_mark_action(status: str, label: str):
    """Bulk admin action: set every selected order to `status` and log the transition."""

    def action(modeladmin, request, queryset):
        updated = 0
        for order in queryset.exclude(status=status):
            order.status = status
            order.save(update_fields=["status", "updated_at"])
            record_status_change(order)
            updated += 1
        modeladmin.message_user(request, f"{updated} order(s) marked {label}.")

    action.__name__ = f"mark_{status}"
    action.short_description = f"Mark selected orders as {label}"
    return action


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "status", "whatsapp_order", "total_amount", "referral_discount_amount",
        "is_gift", "abandoned_reminder_sent_at", "created_at",
    ]
    list_filter = ["status", "is_gift"]
    search_fields = ["id", "user__email"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    actions = [
        _make_mark_action(OrderStatus.CONFIRMED, "Confirmed (payment received)"),
        _make_mark_action(OrderStatus.PROCESSING, "Processing"),
        _make_mark_action(OrderStatus.SHIPPED, "Shipped"),
        _make_mark_action(OrderStatus.DELIVERED, "Delivered"),
        _make_mark_action(OrderStatus.CANCELLED, "Cancelled"),
    ]

    @admin.display(description="WhatsApp?", boolean=True)
    def whatsapp_order(self, obj):
        return obj.status == OrderStatus.AWAITING_DETAILS or obj.address_id is None


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
