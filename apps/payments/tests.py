from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Address, Order
from apps.payments.models import Payment, PaymentStatus
from apps.products.models import Category, Product
from apps.users.models import User


class PaymentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=category, name="Kunafa Chocolate", price=300, stock_quantity=5)
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.order = Order.objects.create(user=self.user, address=self.address, subtotal_amount=300, total_amount=300)

    def test_initiate_manual_payment(self):
        response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "manual"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["payment"]["status"], "pending")
        self.assertIn("upi_id", response.data["data"]["gateway_data"])

    def test_cod_is_no_longer_accepted(self):
        response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "cod"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_initiate_razorpay_not_implemented_yet(self):
        response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "razorpay"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_initiate_payment_for_others_order(self):
        other_user = User.objects.create_user(email="other@example.com", password="StrongPass123!", full_name="Other")
        self.client.force_authenticate(user=other_user)
        response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "manual"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payment_details_endpoint_is_public(self):
        self.client.logout()
        response = self.client.get(reverse("payment-details-info"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("upi_id", response.data["data"])

    def test_marking_payment_successful_confirms_order(self):
        payment = Payment.objects.create(order=self.order, gateway="manual", amount=self.order.total_amount)
        payment.status = PaymentStatus.SUCCESS
        payment.save()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    def test_marking_payment_successful_confirms_whatsapp_order(self):
        """
        WhatsApp-checkout orders start with no address and status
        'awaiting_details' - once staff fill in the address (given in chat)
        and mark the payment successful, the same signal should confirm it.
        """
        wa_order = Order.objects.create(
            user=self.user, address=None, status="awaiting_details",
            subtotal_amount=300, total_amount=300,
        )
        wa_order.address = self.address
        wa_order.save(update_fields=["address"])

        payment = Payment.objects.create(order=wa_order, gateway="manual", amount=wa_order.total_amount)
        payment.status = PaymentStatus.SUCCESS
        payment.save()

        wa_order.refresh_from_db()
        self.assertEqual(wa_order.status, "confirmed")
