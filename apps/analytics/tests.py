from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.analytics.models import PageView
from apps.users.models import Role

User = get_user_model()


class GeoCaptureTests(APITestCase):
    """
    Location is read from the edge proxy's request headers, never from the
    request body - see apps.analytics.geo.
    """

    def setUp(self):
        cache.clear()
        self.url = reverse("pageview-create")

    def test_vercel_headers_are_recorded_with_the_state_name_expanded(self):
        response = self.client.post(
            self.url,
            {"path": "/products", "visitor_id": "v1"},
            HTTP_X_VERCEL_IP_CITY="Jaipur",
            HTTP_X_VERCEL_IP_COUNTRY_REGION="RJ",
            HTTP_X_VERCEL_IP_COUNTRY="IN",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        view = PageView.objects.get()
        self.assertEqual(view.city, "Jaipur")
        # "RJ" on the wire should read as "Rajasthan" on the dashboard.
        self.assertEqual(view.region, "Rajasthan")
        self.assertEqual(view.country, "IN")

    def test_percent_encoded_city_is_decoded(self):
        """Vercel sends "New Delhi" as "New%20Delhi"."""
        self.client.post(
            self.url,
            {"path": "/", "visitor_id": "v2"},
            HTTP_X_VERCEL_IP_CITY="New%20Delhi",
            HTTP_X_VERCEL_IP_COUNTRY_REGION="DL",
            HTTP_X_VERCEL_IP_COUNTRY="IN",
        )
        view = PageView.objects.get()
        self.assertEqual(view.city, "New Delhi")
        self.assertEqual(view.region, "Delhi")

    def test_a_client_cannot_claim_its_own_location(self):
        """The serializer doesn't expose these fields, so a forged body is ignored."""
        self.client.post(
            self.url,
            {"path": "/", "visitor_id": "v3", "city": "Fakeville", "region": "Nowhere", "country": "ZZ"},
        )
        view = PageView.objects.get()
        self.assertEqual(view.city, "")
        self.assertEqual(view.region, "")
        self.assertEqual(view.country, "")

    def test_missing_headers_record_no_location_rather_than_guessing(self):
        self.client.post(self.url, {"path": "/", "visitor_id": "v4"})
        view = PageView.objects.get()
        self.assertEqual((view.city, view.region, view.country), ("", "", ""))

    def test_cloudflare_headers_also_work(self):
        self.client.post(
            self.url,
            {"path": "/", "visitor_id": "v5"},
            HTTP_CF_IPCITY="Udaipur", HTTP_CF_REGION_CODE="RJ", HTTP_CF_IPCOUNTRY="IN",
        )
        view = PageView.objects.get()
        self.assertEqual((view.city, view.region), ("Udaipur", "Rajasthan"))

    def test_no_ip_address_is_stored_anywhere_on_the_row(self):
        self.client.post(
            self.url, {"path": "/", "visitor_id": "v6"},
            HTTP_X_VERCEL_IP_CITY="Jaipur", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="203.0.113.9",
        )
        view = PageView.objects.get()
        stored = " ".join(str(getattr(view, f.name)) for f in PageView._meta.fields)
        self.assertNotIn("203.0.113.9", stored)


class DashboardAccessTests(APITestCase):
    """The dashboard is admin-only - it's wrapped in admin.site.admin_view."""

    def setUp(self):
        self.url = reverse("admin:dashboard")

    def test_anonymous_is_redirected_to_the_admin_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/admin/login/", response["Location"])

    def test_a_signed_in_customer_cannot_open_it(self):
        User.objects.create_user(email="cust@example.com", password="StrongPass123!", full_name="Cust")
        self.client.login(email="cust@example.com", password="StrongPass123!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_staff_sees_the_traffic_tables(self):
        User.objects.create_user(
            email="owner@example.com", password="StrongPass123!", full_name="Owner",
            role=Role.ADMIN, is_staff=True, is_superuser=True,
        )
        self.client.login(email="owner@example.com", password="StrongPass123!")
        PageView.objects.create(path="/", visitor_id="v1", city="Jaipur", region="Rajasthan", country="IN")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Visitors by day", body)
        self.assertIn("Jaipur", body)
        self.assertIn("Rajasthan", body)

    def test_seven_days_are_always_listed_even_with_no_traffic(self):
        User.objects.create_user(
            email="owner2@example.com", password="StrongPass123!", full_name="Owner",
            role=Role.ADMIN, is_staff=True, is_superuser=True,
        )
        self.client.login(email="owner2@example.com", password="StrongPass123!")
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["traffic_by_day"]), 7)
        self.assertEqual(response.context["traffic_by_day"][0]["label"], "Today")
        self.assertEqual(response.context["traffic_by_day"][1]["label"], "Yesterday")
