from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.products.models import Category, Product
from apps.users.models import User


class ProductTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Ladoo")
        self.product = Product.objects.create(
            category=self.category,
            name="Besan Ladoo",
            price=299,
            stock_quantity=10,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com", password="StrongPass123!", full_name="Admin", role="admin"
        )
        self.customer = User.objects.create_user(
            email="customer@example.com", password="StrongPass123!", full_name="Customer"
        )

    def test_public_can_list_products(self):
        response = self.client.get(reverse("product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_customer_cannot_create_product(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse("product-list"), {
            "name": "New Sweet", "category_id": self.category.id, "price": 199,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_product(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(reverse("product-list"), {
            "name": "New Sweet", "category_id": self.category.id, "price": 199,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 2)

    def test_inactive_product_hidden_from_public(self):
        self.product.is_active = False
        self.product.save()
        response = self.client.get(reverse("product-list"))
        self.assertEqual(response.data["data"]["count"], 0)
