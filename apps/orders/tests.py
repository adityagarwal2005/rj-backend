from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders import services
from apps.orders.models import Address, Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus
from apps.products.models import Category, Product
from apps.users.models import ReferralCredit, User


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

    def test_no_discount_without_applying_a_code(self):
        """price=300, qty=2 -> subtotal=600, but no promo code applied -> no discount."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "600.00")
        self.assertEqual(data["discount_amount"], "0.00")
        self.assertEqual(data["total_amount"], "600.00")

    def test_checkout_applies_discount_from_code_on_cart(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        self.client.post(reverse("cart-promo"), {"code": "SAVE20"})
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


class PromoCodeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=200, stock_quantity=10)

    def test_apply_code_customer_qualifies_for(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("cart-promo"), {"code": "save10"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["applied_promo_code"], "SAVE10")
        self.assertEqual(data["discount_percentage"], "10.00")
        self.assertEqual(data["total_amount"], Decimal("180.00"))

    def test_apply_code_customer_does_not_yet_qualify_for(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("cart-promo"), {"code": "SAVE20"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_apply_unknown_code(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("cart-promo"), {"code": "NOTREAL"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_applied_code(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("cart-promo"), {"code": "SAVE10"})
        response = self.client.delete(reverse("cart-promo"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["applied_promo_code"], "")
        self.assertEqual(response.data["data"]["discount_amount"], "0.00")

    def test_applied_code_stops_discounting_if_cart_drops_below_threshold(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        self.client.post(reverse("cart-promo"), {"code": "SAVE20"})
        cart_response = self.client.get(reverse("cart-detail"))
        item_id = cart_response.data["data"]["items"][0]["id"]
        response = self.client.patch(reverse("cart-item-detail", args=[item_id]), {"quantity": 1})
        data = response.data["data"]
        self.assertEqual(data["applied_promo_code"], "SAVE20")
        self.assertEqual(data["discount_amount"], "0.00")

    def test_checkout_requires_reapplying_code_after_order_placed(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("cart-promo"), {"code": "SAVE10"})
        address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.client.post(reverse("order-list"), {"address_id": address.id})

        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(cart_response.data["data"]["applied_promo_code"], "")


class ReferralProgramTests(APITestCase):
    def setUp(self):
        self.referrer = User.objects.create_user(email="friend@example.com", password="StrongPass123!", full_name="Friend")
        self.user = User.objects.create_user(
            email="cust@example.com", password="StrongPass123!", full_name="Cust", referred_by=self.referrer,
        )
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=150, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def test_referee_gets_discount_on_first_order(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["referral_discount_amount"], "30.00")
        self.assertEqual(data["total_amount"], "120.00")

    def test_referee_discount_does_not_apply_on_second_order(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("order-list"), {"address_id": self.address.id})

        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.data["data"]["referral_discount_amount"], "0.00")

    def test_referrer_earns_credit_when_referee_order_is_confirmed(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        payment = Payment.objects.create(order_id=order_id, gateway="manual", amount=120)
        payment.status = PaymentStatus.SUCCESS
        payment.save()

        self.assertTrue(ReferralCredit.objects.filter(user=self.referrer, amount=30, is_used=False).exists())
        self.user.refresh_from_db()
        self.assertTrue(self.user.referral_reward_granted)

    def test_referrer_credit_is_redeemed_on_next_order(self):
        ReferralCredit.objects.create(user=self.referrer, amount=30)
        self.client.force_authenticate(user=self.referrer)
        Address.objects.create(
            user=self.referrer, full_name="Friend", phone="9999999999",
            line1="1 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        referrer_address = self.referrer.addresses.first()

        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": referrer_address.id})

        self.assertEqual(response.data["data"]["referral_discount_amount"], "30.00")
        self.assertTrue(ReferralCredit.objects.get(user=self.referrer).is_used)

    def test_cancelling_order_restores_unspent_referral_credit(self):
        ReferralCredit.objects.create(user=self.referrer, amount=30)
        self.client.force_authenticate(user=self.referrer)
        Address.objects.create(
            user=self.referrer, full_name="Friend", phone="9999999999",
            line1="1 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        referrer_address = self.referrer.addresses.first()

        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": referrer_address.id})
        order_id = order_response.data["data"]["id"]

        self.client.post(reverse("order-cancel", args=[order_id]))

        credit = ReferralCredit.objects.get(user=self.referrer)
        self.assertFalse(credit.is_used)
        self.assertIsNone(credit.used_on_order_id)

    def test_cart_preview_includes_referral_discount(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.get(reverse("cart-detail"))
        self.assertEqual(response.data["data"]["referral_discount_amount"], Decimal("30"))
        self.assertEqual(response.data["data"]["total_amount"], Decimal("120"))


class AbandonedOrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=200, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.order = Order.objects.create(
            user=self.user, address=self.address, status=OrderStatus.PENDING,
            subtotal_amount=200, total_amount=200,
        )

    def test_recent_pending_order_is_not_reminded_yet(self):
        count = services.send_abandoned_order_reminders()
        self.assertEqual(count, 0)

    def test_stale_pending_order_gets_one_reminder_only(self):
        Order.objects.filter(id=self.order.id).update(created_at=timezone.now() - timedelta(hours=3))

        count = services.send_abandoned_order_reminders()
        self.assertEqual(count, 1)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.abandoned_reminder_sent_at)

        count_again = services.send_abandoned_order_reminders()
        self.assertEqual(count_again, 0)

    def test_very_stale_order_is_auto_cancelled(self):
        Order.objects.filter(id=self.order.id).update(created_at=timezone.now() - timedelta(hours=49))

        count = services.auto_cancel_stale_pending_orders()
        self.assertEqual(count, 1)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)

    def test_recent_pending_order_is_not_auto_cancelled(self):
        count = services.auto_cancel_stale_pending_orders()
        self.assertEqual(count, 0)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)


class ProcessAbandonedOrdersEndpointTests(APITestCase):
    @override_settings(CRON_SECRET="test-secret")
    def test_rejects_missing_or_wrong_secret(self):
        response = self.client.post(reverse("process-abandoned-orders"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(reverse("process-abandoned-orders"), HTTP_X_CRON_SECRET="wrong")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CRON_SECRET="test-secret")
    def test_accepts_correct_secret(self):
        response = self.client.post(reverse("process-abandoned-orders"), HTTP_X_CRON_SECRET="test-secret")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("reminded", response.data["data"])
        self.assertIn("cancelled", response.data["data"])

    def test_rejects_everything_when_no_secret_configured(self):
        response = self.client.post(reverse("process-abandoned-orders"), HTTP_X_CRON_SECRET="")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
