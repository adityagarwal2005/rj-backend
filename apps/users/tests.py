from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User


class AuthTests(APITestCase):
    def setUp(self):
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.profile_url = reverse("auth-profile")

    def test_register_creates_user_and_returns_tokens(self):
        payload = {
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "StrongPass123!",
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIn("access", response.data["data"])
        self.assertEqual(User.objects.count(), 1)

    def test_login_with_valid_credentials(self):
        User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")
        response = self.client.post(
            self.login_url, {"email": "test@example.com", "password": "StrongPass123!"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

    def test_login_with_invalid_credentials(self):
        response = self.client.post(
            self.login_url, {"email": "nouser@example.com", "password": "wrong"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])

    def test_profile_requires_authentication(self):
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_returns_authenticated_user(self):
        user = User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")
        self.client.force_authenticate(user=user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["email"], "test@example.com")
