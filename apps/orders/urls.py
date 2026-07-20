from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.orders.views import (
    AddressViewSet,
    CartItemDetailView,
    CartItemListView,
    CartView,
    OrderViewSet,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart-detail"),
    path("cart/items/", CartItemListView.as_view(), name="cart-item-list"),
    path("cart/items/<int:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
] + router.urls
