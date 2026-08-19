from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Address, Order, OrderItem, OrderStatus
from apps.products.models import Category, Product, Review, WishlistItem
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

    def test_product_list_shows_is_wishlisted_false_for_anonymous(self):
        response = self.client.get(reverse("product-list"))
        self.assertFalse(response.data["data"]["results"][0]["is_wishlisted"])


class BulkPricingTests(APITestCase):
    """price_for_quantity: buy 1 at the base price, 2+ at the bulk per-unit price."""

    def setUp(self):
        category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(
            category=category, name="Kunafa Chocolate", price=120, stock_quantity=10,
            bulk_price=110, bulk_min_quantity=2,
        )

    def test_single_unit_uses_base_price(self):
        self.assertEqual(self.product.price_for_quantity(1), 120)

    def test_bulk_quantity_uses_bulk_price(self):
        self.assertEqual(self.product.price_for_quantity(2), 110)
        self.assertEqual(self.product.price_for_quantity(5), 110)

    def test_no_bulk_price_set_always_uses_effective_price(self):
        plain = Product.objects.create(category=self.product.category, name="Plain Bar", price=200, stock_quantity=5)
        self.assertEqual(plain.price_for_quantity(1), 200)
        self.assertEqual(plain.price_for_quantity(10), 200)

    def test_bulk_price_ignored_below_min_quantity(self):
        self.product.bulk_min_quantity = 3
        self.product.save(update_fields=["bulk_min_quantity"])
        self.assertEqual(self.product.price_for_quantity(2), 120)
        self.assertEqual(self.product.price_for_quantity(3), 110)


class WishlistTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=self.category, name="Kunafa Chocolate", price=200, stock_quantity=10)
        self.other_product = Product.objects.create(category=self.category, name="Other Bar", price=150, stock_quantity=10)
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)

    def test_anonymous_cannot_wishlist(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_to_wishlist(self):
        response = self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["data"]["is_wishlisted"])
        self.assertTrue(WishlistItem.objects.filter(user=self.user, product=self.product).exists())

    def test_adding_twice_does_not_duplicate(self):
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.assertEqual(WishlistItem.objects.filter(user=self.user, product=self.product).count(), 1)

    def test_remove_from_wishlist(self):
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        response = self.client.delete(reverse("product-wishlist", args=[self.product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["data"]["is_wishlisted"])
        self.assertFalse(WishlistItem.objects.filter(user=self.user, product=self.product).exists())

    def test_product_detail_reflects_wishlist_status(self):
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        response = self.client.get(reverse("product-detail", args=[self.product.slug]))
        self.assertTrue(response.data["data"]["is_wishlisted"])

    def test_wishlist_is_scoped_per_user(self):
        other_user = User.objects.create_user(email="other@example.com", password="StrongPass123!", full_name="Other")
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.client.force_authenticate(user=other_user)
        response = self.client.get(reverse("product-detail", args=[self.product.slug]))
        self.assertFalse(response.data["data"]["is_wishlisted"])

    def test_my_wishlist_lists_only_wishlisted_products_most_recent_first(self):
        self.client.post(reverse("product-wishlist", args=[self.product.slug]))
        self.client.post(reverse("product-wishlist", args=[self.other_product.slug]))
        response = self.client.get(reverse("product-my-wishlist"))
        names = [item["name"] for item in response.data["data"]["results"]]
        self.assertEqual(names, ["Other Bar", "Kunafa Chocolate"])

    def test_my_wishlist_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("product-my-wishlist"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ReviewTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Chocolates")
        self.product = Product.objects.create(category=self.category, name="Kunafa Chocolate", price=200, stock_quantity=10)
        self.other_product = Product.objects.create(category=self.category, name="Other Bar", price=200, stock_quantity=10)
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.address = Address.objects.create(
            user=self.user, full_name="Cust", phone="9999999999",
            line1="123 Street", city="Jaipur", state="Rajasthan", postal_code="302001",
        )

    def _delivered_order(self, product=None):
        order = Order.objects.create(
            user=self.user, address=self.address, status=OrderStatus.DELIVERED,
            subtotal_amount=200, total_amount=200,
        )
        OrderItem.objects.create(
            order=order, product=product or self.product, product_name="Kunafa Chocolate",
            unit_price=200, quantity=1,
        )
        return order

    def test_public_can_list_reviews(self):
        order = self._delivered_order()
        Review.objects.create(product=self.product, order=order, user=self.user, rating=5, comment="Great!")
        response = self.client.get(reverse("product-reviews", args=[self.product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anonymous_cannot_submit_review(self):
        order = self._delivered_order()
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {
            "order_id": order.id, "rating": 5, "comment": "Loved it",
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_can_review_a_delivered_order(self):
        order = self._delivered_order()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {
            "order_id": order.id, "rating": 5, "comment": "Loved it",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Review.objects.count(), 1)

        product_response = self.client.get(reverse("product-detail", args=[self.product.slug]))
        self.assertEqual(product_response.data["data"]["average_rating"], 5.0)
        self.assertEqual(product_response.data["data"]["review_count"], 1)

    def test_cannot_review_a_non_delivered_order(self):
        order = Order.objects.create(
            user=self.user, address=self.address, status=OrderStatus.PENDING,
            subtotal_amount=200, total_amount=200,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name="Kunafa Chocolate", unit_price=200, quantity=1,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {
            "order_id": order.id, "rating": 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_review_a_product_not_in_the_order(self):
        order = self._delivered_order(product=self.other_product)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {
            "order_id": order.id, "rating": 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_review_the_same_order_product_twice(self):
        order = self._delivered_order()
        self.client.force_authenticate(user=self.user)
        self.client.post(reverse("product-reviews", args=[self.product.slug]), {"order_id": order.id, "rating": 5})
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {"order_id": order.id, "rating": 3})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_review_someone_elses_order(self):
        other_user = User.objects.create_user(email="other@example.com", password="StrongPass123!", full_name="Other")
        order = self._delivered_order()
        self.client.force_authenticate(user=other_user)
        response = self.client.post(reverse("product-reviews", args=[self.product.slug]), {
            "order_id": order.id, "rating": 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
