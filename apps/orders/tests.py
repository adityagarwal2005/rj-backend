from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Address, Order
from apps.products.models import Category, Product
from apps.users.models import User


class CartAndCheckoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Ladoo")
        self.product = Product.objects.create(category=category, name="Besan Ladoo", price=300, stock_quantity=5)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def test_add_item_to_cart(self):
        response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["data"]["items"]), 1)

    def test_checkout_decrements_stock_and_clears_cart(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertEqual(Order.objects.count(), 1)

        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(len(cart_response.data["data"]["items"]), 0)

    def test_order_stays_pending_until_payment_is_confirmed(self):
        """Prepaid-only business: checkout doesn't auto-confirm the order anymore."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.data["data"]["status"], "pending")

    def test_checkout_applies_discount_tier(self):
        """price=300, qty=2 -> subtotal=600 -> highest tier (>=400) is 20% off."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "600.00")
        self.assertEqual(data["discount_percentage"], "20.00")
        self.assertEqual(data["discount_amount"], "120.00")
        self.assertEqual(data["total_amount"], "480.00")

    def test_no_discount_below_lowest_tier(self):
        cheap_product = Product.objects.create(
            category=self.product.category, name="Mini Bite", price=150, stock_quantity=5
        )
        self.client.post(reverse("cart-item-list"), {"product_id": cheap_product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["discount_amount"], "0.00")
        self.assertEqual(data["total_amount"], "150.00")

    def test_address_outside_jaipur_is_rejected(self):
        response = self.client.post(reverse("address-list"), {
            "full_name": "Cust", "phone": "9999999999", "line1": "1 MG Road",
            "city": "Mumbai", "state": "Maharashtra", "postal_code": "400001",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_fails_on_insufficient_stock(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 10})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_fails_with_empty_cart(self):
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_order_restores_stock(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        response = self.client.post(reverse("order-cancel", args=[order_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_whatsapp_checkout_creates_order_without_address(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-checkout-whatsapp"), {"notes": "call me"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(data["status"], "awaiting_details")
        self.assertIsNone(data["address"])

    def test_whatsapp_checkout_decrements_stock_and_clears_cart(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-checkout-whatsapp"))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(len(cart_response.data["data"]["items"]), 0)

    def test_whatsapp_checkout_fails_with_empty_cart(self):
        response = self.client.post(reverse("order-checkout-whatsapp"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
