from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.orders.views import (
    AddressViewSet,
    CartItemDetailView,
    CartItemListView,
    CartPromoView,
    CartView,
    OrderViewSet,
    ProcessAbandonedOrdersView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart-detail"),
    path("cart/items/", CartItemListView.as_view(), name="cart-item-list"),
    path("cart/items/<int:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("cart/promo/", CartPromoView.as_view(), name="cart-promo"),
    # Must come before router.urls - OrderViewSet's default pk lookup regex
    # would otherwise swallow this as a detail route (pk="process-abandoned").
    path("process-abandoned/", ProcessAbandonedOrdersView.as_view(), name="process-abandoned-orders"),
] + router.urls
