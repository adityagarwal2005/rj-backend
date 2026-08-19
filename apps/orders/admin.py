from django.contrib import admin

from apps.orders.models import Address, Cart, CartItem, Order, OrderItem, OrderStatus, OrderStatusHistory
from apps.orders.services import record_status_change
from apps.payments.models import PaymentGatewayChoice


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "created_at"]
    can_delete = False


class PaymentMethodFilter(admin.SimpleListFilter):
    """Lets staff filter the order list to just UPI/manual, COD, or Razorpay orders."""

    title = "payment method"
    parameter_name = "payment_method"

    def lookups(self, request, model_admin):
        return PaymentGatewayChoice.choices

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(payments__gateway=self.value()).distinct()


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
        "id", "user", "status", "payment_method", "whatsapp_order", "total_amount", "referral_discount_amount",
        "is_gift", "abandoned_reminder_sent_at", "created_at",
    ]
    list_filter = ["status", PaymentMethodFilter, "is_gift"]
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

    @admin.display(description="Payment method")
    def payment_method(self, obj):
        payment = obj.payments.order_by("-created_at").first()
        if payment is None:
            return "—"
        return f"{payment.get_gateway_display()} ({payment.get_status_display()})"

    def get_queryset(self, request):
        # Avoids one extra query per row for the payment_method column above.
        return super().get_queryset(request).prefetch_related("payments")


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
