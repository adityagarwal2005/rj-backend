from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.users.models import User


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.force_authenticate(user=self.user)
        self.notification = Notification.objects.create(user=self.user, title="Hi", message="Welcome!")

    def test_list_notifications(self):
        response = self.client.get(reverse("notification-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_mark_notification_read(self):
        url = reverse("notification-mark-read", args=[self.notification.id])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
