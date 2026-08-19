from datetime import timedelta
from decimal import Decimal

from django.core import mail
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
        self.assertEqual(response.data["data"]["items"][0]["stock_quantity"], 5)

    def test_cannot_add_more_than_available_stock(self):
        response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 6})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(len(cart_response.data["data"]["items"]), 0)

    def test_cannot_add_more_than_stock_across_two_calls(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 3})
        response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 3})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(cart_response.data["data"]["items"][0]["quantity"], 3)

    def test_cannot_update_cart_item_past_available_stock(self):
        add_response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        item_id = add_response.data["data"]["items"][0]["id"]
        response = self.client.patch(reverse("cart-item-detail", args=[item_id]), {"quantity": 6})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        cart_response = self.client.get(reverse("cart-detail"))
        self.assertEqual(cart_response.data["data"]["items"][0]["quantity"], 2)

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

    def test_no_discount_below_bulk_threshold(self):
        """price=300, qty=2 -> subtotal=600, below the 800 bulk-discount threshold -> no discount."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "600.00")
        self.assertEqual(data["discount_amount"], "0.00")
        self.assertEqual(data["total_amount"], "600.00")

    def test_checkout_applies_automatic_bulk_discount(self):
        """price=300, qty=3 -> subtotal=900, crosses the 800 threshold -> automatic 5% off, no code needed."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 3})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "900.00")
        self.assertEqual(data["discount_percentage"], "5.00")
        self.assertEqual(data["discount_amount"], "45.00")
        self.assertEqual(data["total_amount"], "855.00")

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


class OrderPlacedCustomerEmailTests(APITestCase):
    """The itemized "thanks for your order" receipt - see notify_order_placed."""

    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=120, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def test_website_order_gets_an_itemized_receipt(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        self.client.post(reverse("order-list"), {"address_id": self.address.id})
        customer_emails = [m for m in mail.outbox if m.to == [self.user.email]]
        self.assertEqual(len(customer_emails), 1)
        email = customer_emails[0]
        self.assertIn("Thanks for your order", email.subject)
        self.assertIn("Kunafa Chocolate", email.body)
        self.assertIn("x 2", email.body)
        self.assertIn("240", email.body)  # total
        self.assertNotIn("WhatsApp", email.body)

    def test_whatsapp_order_receipt_mentions_the_followup(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("order-checkout-whatsapp"))
        customer_emails = [m for m in mail.outbox if m.to == [self.user.email]]
        self.assertEqual(len(customer_emails), 1)
        self.assertIn("WhatsApp", customer_emails[0].body)


class AdminNewOrderAlertTests(APITestCase):
    """The one notification that reaches the store owner, not the customer - see notify_admin_new_order."""

    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=120, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    @override_settings(ADMIN_EMAIL="owner@example.com")
    def test_website_checkout_emails_the_admin(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("order-list"), {"address_id": self.address.id})
        admin_emails = [m for m in mail.outbox if m.to == ["owner@example.com"]]
        self.assertEqual(len(admin_emails), 1)
        self.assertIn("website", admin_emails[0].subject.lower())

    @override_settings(ADMIN_EMAIL="owner@example.com")
    def test_whatsapp_checkout_emails_the_admin(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        self.client.post(reverse("order-checkout-whatsapp"))
        admin_emails = [m for m in mail.outbox if m.to == ["owner@example.com"]]
        self.assertEqual(len(admin_emails), 1)
        self.assertIn("whatsapp", admin_emails[0].subject.lower())

    @override_settings(ADMIN_EMAIL="")
    def test_no_admin_email_configured_is_a_silent_noop(self):
        """Order creation still emails the customer (notify_order_placed) - just never the (unset) admin."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)  # the customer's "order placed" email only
        self.assertEqual(mail.outbox[0].to, [self.user.email])


class BulkUnitPricingTests(APITestCase):
    """Per-product quantity price break (e.g. 120 for 1, 110/unit for 2+) - distinct from the order-level bulk discount below."""

    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(
            category=category, name="Kunafa Chocolate", price=120, stock_quantity=10,
            bulk_price=110, bulk_min_quantity=2,
        )

    def test_cart_reflects_base_price_for_single_unit(self):
        response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        item = response.data["data"]["items"][0]
        self.assertEqual(item["unit_price"], "120.00")
        self.assertEqual(item["subtotal"], "120.00")

    def test_cart_reflects_bulk_price_for_two_or_more(self):
        response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        item = response.data["data"]["items"][0]
        self.assertEqual(item["unit_price"], "110.00")
        self.assertEqual(item["subtotal"], "220.00")

    def test_checkout_snapshots_the_bulk_unit_price(self):
        address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 2})
        response = self.client.post(reverse("order-list"), {"address_id": address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "220.00")
        order_item = data["items"][0]
        self.assertEqual(order_item["unit_price"], "110.00")


class BulkDiscountTests(APITestCase):
    """The 5%-off-orders-over-800 discount is automatic - no code to apply/remove."""

    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=200, stock_quantity=10)

    def test_no_discount_below_threshold(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 3})
        response = self.client.get(reverse("cart-detail"))
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "600.00")
        self.assertEqual(data["discount_amount"], "0.00")

    def test_discount_applies_automatically_once_threshold_crossed(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 4})
        response = self.client.get(reverse("cart-detail"))
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "800.00")
        self.assertEqual(data["discount_percentage"], "5.00")
        self.assertEqual(data["discount_amount"], "40.00")
        self.assertEqual(data["total_amount"], Decimal("760.00"))

    def test_discount_disappears_if_cart_drops_below_threshold(self):
        add_response = self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 4})
        item_id = add_response.data["data"]["items"][0]["id"]
        response = self.client.patch(reverse("cart-item-detail", args=[item_id]), {"quantity": 2})
        data = response.data["data"]
        self.assertEqual(data["discount_amount"], "0.00")

    def test_checkout_freezes_the_automatic_discount_on_the_order(self):
        address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 5})
        response = self.client.post(reverse("order-list"), {"address_id": address.id})
        data = response.data["data"]
        self.assertEqual(data["subtotal_amount"], "1000.00")
        self.assertEqual(data["discount_percentage"], "5.00")
        self.assertEqual(data["discount_amount"], "50.00")
        self.assertEqual(data["total_amount"], "950.00")


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


class GiftOrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=200, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def test_checkout_with_gift_details(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {
            "address_id": self.address.id, "is_gift": True, "gift_message": "Happy birthday!",
        })
        data = response.data["data"]
        self.assertTrue(data["is_gift"])
        self.assertEqual(data["gift_message"], "Happy birthday!")

    def test_gift_message_dropped_when_not_a_gift(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {
            "address_id": self.address.id, "is_gift": False, "gift_message": "Should not be saved",
        })
        data = response.data["data"]
        self.assertFalse(data["is_gift"])
        self.assertEqual(data["gift_message"], "")

    def test_checkout_defaults_to_not_a_gift(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        data = response.data["data"]
        self.assertFalse(data["is_gift"])
        self.assertEqual(data["gift_message"], "")

    def test_cannot_edit_order_via_generic_patch(self):
        """Order mutation must go through cancel/status, not a direct PATCH - see OrderViewSet.partial_update."""
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        response = self.client.patch(reverse("order-detail", args=[order_id]), {"notes": "hacked"})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        order_response = self.client.get(reverse("order-detail", args=[order_id]))
        self.assertEqual(order_response.data["data"]["notes"], "")


class OrderStatusHistoryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.admin = User.objects.create_user(
            email="admin@example.com", password="StrongPass123!", full_name="Admin", role="admin"
        )
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=200, stock_quantity=10)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def test_order_creation_logs_initial_status(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        history = response.data["data"]["status_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "pending")

    def test_payment_confirmation_logs_status_change(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        payment = Payment.objects.create(order_id=order_id, gateway="manual", amount=200)
        payment.status = PaymentStatus.SUCCESS
        payment.save()

        detail_response = self.client.get(reverse("order-detail", args=[order_id]))
        statuses = [entry["status"] for entry in detail_response.data["data"]["status_history"]]
        self.assertEqual(statuses, ["pending", "confirmed"])

    def test_admin_status_update_logs_change(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(reverse("order-update-status", args=[order_id]), {"status": "shipped"})
        statuses = [entry["status"] for entry in response.data["data"]["status_history"]]
        self.assertEqual(statuses, ["pending", "shipped"])

    def test_cancellation_logs_status_change(self):
        self.client.post(reverse("cart-item-list"), {"product_id": self.product.id, "quantity": 1})
        order_response = self.client.post(reverse("order-list"), {"address_id": self.address.id})
        order_id = order_response.data["data"]["id"]

        response = self.client.post(reverse("order-cancel", args=[order_id]))
        statuses = [entry["status"] for entry in response.data["data"]["status_history"]]
        self.assertEqual(statuses, ["pending", "cancelled"])


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
