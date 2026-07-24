import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import razorpay
from django.test import override_settings
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

    def test_submit_utr_for_own_pending_payment(self):
        payment = Payment.objects.create(order=self.order, gateway="manual", amount=self.order.total_amount)
        response = self.client.post(reverse("payment-submit-utr"), {"order_id": self.order.id, "utr_reference": "123456789012"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.utr_reference, "123456789012")

    def test_submit_utr_rejects_other_users_order(self):
        Payment.objects.create(order=self.order, gateway="manual", amount=self.order.total_amount)
        other_user = User.objects.create_user(email="other2@example.com", password="StrongPass123!", full_name="Other")
        self.client.force_authenticate(user=other_user)
        response = self.client.post(reverse("payment-submit-utr"), {"order_id": self.order.id, "utr_reference": "123456789012"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_utr_without_pending_payment_returns_404(self):
        response = self.client.post(reverse("payment-submit-utr"), {"order_id": self.order.id, "utr_reference": "123456789012"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

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


@override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="test_secret", RAZORPAY_WEBHOOK_SECRET="whsec_test")
class RazorpayGatewayTests(APITestCase):
    """
    Razorpay isn't wired to real keys yet (KYC pending), so every network
    call here is mocked - these tests exist to prove the integration code
    itself (order creation, signature verification, webhook handling) is
    correct ahead of flipping real keys into the env.
    """

    def setUp(self):
        self.user = User.objects.create_user(email="rzp@example.com", password="StrongPass123!", full_name="Rzp")
        self.client.force_authenticate(user=self.user)
        category = Category.objects.create(name="Chocolates")
        Product.objects.create(category=category, name="Kunafa Chocolate", price=300, stock_quantity=5)
        self.address = Address.objects.create(
            user=self.user, full_name="Rzp", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )
        self.order = Order.objects.create(user=self.user, address=self.address, subtotal_amount=300, total_amount=300)

    @patch("apps.payments.services.razorpay.Client")
    def test_initiate_razorpay_payment_creates_gateway_order(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_ABC123"}
        mock_client_cls.return_value = mock_client

        response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "razorpay"})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["gateway_data"]["razorpay_order_id"], "order_ABC123")
        self.assertEqual(response.data["data"]["gateway_data"]["amount"], 30000)
        payment = Payment.objects.get(id=response.data["data"]["payment"]["id"])
        self.assertEqual(payment.gateway_order_id, "order_ABC123")

    @patch("apps.payments.services.razorpay.Client")
    def test_checkout_callback_confirms_order_on_valid_signature(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_ABC123"}
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client_cls.return_value = mock_client

        init_response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "razorpay"})
        payment_id = init_response.data["data"]["payment"]["id"]

        response = self.client.post(
            reverse("payment-webhook", args=[payment_id]),
            {"gateway_payment_id": "pay_XYZ", "gateway_signature": "sig_XYZ"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    @patch("apps.payments.services.razorpay.Client")
    def test_checkout_callback_rejects_invalid_signature(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_ABC123"}
        mock_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError("bad sig")
        mock_client_cls.return_value = mock_client

        init_response = self.client.post(reverse("payment-initiate"), {"order_id": self.order.id, "gateway": "razorpay"})
        payment_id = init_response.data["data"]["payment"]["id"]

        response = self.client.post(
            reverse("payment-webhook", args=[payment_id]),
            {"gateway_payment_id": "pay_XYZ", "gateway_signature": "bad"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment = Payment.objects.get(id=payment_id)
        self.assertEqual(payment.status, "failed")

    def test_razorpay_server_webhook_confirms_order(self):
        payment = Payment.objects.create(
            order=self.order, gateway="razorpay", amount=self.order.total_amount, gateway_order_id="order_ABC123",
        )
        body = json.dumps(
            {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_XYZ", "order_id": "order_ABC123"}}}}
        ).encode()
        signature = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("razorpay-server-webhook"), data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "success")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    def test_razorpay_server_webhook_rejects_bad_signature(self):
        payment = Payment.objects.create(
            order=self.order, gateway="razorpay", amount=self.order.total_amount, gateway_order_id="order_ABC123",
        )
        body = json.dumps(
            {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_XYZ", "order_id": "order_ABC123"}}}}
        ).encode()

        response = self.client.post(
            reverse("razorpay-server-webhook"), data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="wrong-signature",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "pending")
