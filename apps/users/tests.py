import re
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users import services
from apps.users.models import EmailOTP, OTPPurpose, User


def _extract_code(body: str) -> str:
    return re.search(r"\b(\d{6})\b", body).group(1)


class AuthTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters persist in the test cache across test methods otherwise
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.profile_url = reverse("auth-profile")

    def test_register_creates_an_inactive_user_and_emails_a_code(self):
        """No tokens back anymore - the account isn't usable until verify-email consumes the OTP."""
        payload = {
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "StrongPass123!",
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("access", response.data["data"])
        user = User.objects.get(email="test@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your email", mail.outbox[0].subject)

    def test_unverified_user_cannot_log_in(self):
        self.client.post(self.register_url, {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
        })
        response = self.client.post(self.login_url, {"email": "test@example.com", "password": "StrongPass123!"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["errors"]["code"], "email_not_verified")

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

    def test_every_new_user_gets_a_unique_referral_code(self):
        self.client.post(self.register_url, {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
        })
        self.assertTrue(User.objects.get(email="test@example.com").referral_code)

    def test_registering_with_a_valid_referral_code_links_the_referrer(self):
        referrer = User.objects.create_user(email="friend@example.com", password="StrongPass123!", full_name="Friend")
        response = self.client.post(self.register_url, {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
            "referral_code": referrer.referral_code,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email="test@example.com")
        self.assertEqual(new_user.referred_by_id, referrer.id)

    def test_registering_with_an_unknown_referral_code_is_rejected(self):
        response = self.client.post(self.register_url, {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
            "referral_code": "NOTREAL1",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReferralSummaryTests(APITestCase):
    def test_referral_summary_reports_code_and_stats(self):
        user = User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("auth-referrals"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["referral_code"], user.referral_code)
        self.assertEqual(response.data["data"]["referred_count"], 0)
        self.assertEqual(response.data["data"]["available_credit"], Decimal("0"))

    def test_referral_summary_requires_authentication(self):
        response = self.client.get(reverse("auth-referrals"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class VerifyEmailTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("auth-verify-email")
        response = self.client.post(reverse("auth-register"), {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user = User.objects.get(email="test@example.com")
        self.code = _extract_code(mail.outbox[0].body)

    def test_correct_code_activates_and_logs_in(self):
        response = self.client.post(self.url, {"email": "test@example.com", "code": self.code})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_wrong_code_is_rejected_and_does_not_activate(self):
        wrong = "000000" if self.code != "000000" else "111111"
        response = self.client.post(self.url, {"email": "test@example.com", "code": wrong})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_code_cannot_be_reused(self):
        self.client.post(self.url, {"email": "test@example.com", "code": self.code})
        response = self.client.post(self.url, {"email": "test@example.com", "code": self.code})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_five_wrong_attempts_locks_out_the_code_even_if_the_sixth_is_correct(self):
        # This test is specifically about EmailOTP.failed_attempts (an
        # application-level lockout), not the "otp" request-rate throttle -
        # clearing the cache between attempts keeps the two independent, or
        # the 6th request would just get network-throttled instead of
        # actually exercising the lockout logic this test targets.
        for _ in range(5):
            self.client.post(self.url, {"email": "test@example.com", "code": "000000"})
            cache.clear()
        response = self.client.post(self.url, {"email": "test@example.com", "code": self.code})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ResendOtpTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_resend_sends_a_fresh_code_for_an_unverified_account(self):
        self.client.post(reverse("auth-register"), {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
        })
        mail.outbox.clear()
        response = self.client.post(reverse("auth-resend-otp"), {"email": "test@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_old_code_stops_working_once_a_new_one_is_sent(self):
        self.client.post(reverse("auth-register"), {
            "email": "test@example.com", "full_name": "Test User", "password": "StrongPass123!",
        })
        old_code = _extract_code(mail.outbox[0].body)
        self.client.post(reverse("auth-resend-otp"), {"email": "test@example.com"})
        response = self.client.post(reverse("auth-verify-email"), {"email": "test@example.com", "code": old_code})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_verified_account_gets_the_same_generic_response_but_no_email(self):
        User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")
        response = self.client.post(reverse("auth-resend-otp"), {"email": "test@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_email_gets_the_same_generic_response(self):
        response = self.client.post(reverse("auth-resend-otp"), {"email": "nobody@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OtpLoginTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")
        self.request_url = reverse("auth-otp-login-request")
        self.verify_url = reverse("auth-otp-login-verify")

    def test_request_then_verify_logs_in_without_a_password(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        code = _extract_code(mail.outbox[0].body)
        response = self.client.post(self.verify_url, {"email": "test@example.com", "code": code})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

    def test_unverified_account_cannot_request_a_login_otp(self):
        self.client.post(reverse("auth-register"), {
            "email": "unverified@example.com", "full_name": "Unverified", "password": "StrongPass123!",
        })
        mail.outbox.clear()
        response = self.client.post(self.request_url, {"email": "unverified@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_is_rejected(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        response = self.client.post(self.verify_url, {"email": "test@example.com", "code": "000000"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_email_gets_generic_response_not_an_error(self):
        response = self.client.post(self.request_url, {"email": "nobody@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="test@example.com", password="OldPass123!", full_name="Test")
        self.request_url = reverse("auth-password-reset-request")
        self.confirm_url = reverse("auth-password-reset-confirm")

    def _get_reset_link_token(self) -> str:
        body = mail.outbox[0].body
        link_line = next(line for line in body.splitlines() if "reset-password" in line)
        return link_line.split("token=")[1].strip()

    def test_request_then_confirm_changes_the_password(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        token = self._get_reset_link_token()
        response = self.client.post(self.confirm_url, {
            "uid": self.user.id, "token": token, "new_password": "BrandNewPass456!",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass456!"))

    def test_can_log_in_with_the_new_password_afterward(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        token = self._get_reset_link_token()
        self.client.post(self.confirm_url, {"uid": self.user.id, "token": token, "new_password": "BrandNewPass456!"})
        response = self.client.post(reverse("auth-login"), {"email": "test@example.com", "password": "BrandNewPass456!"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_token_cannot_be_reused(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        token = self._get_reset_link_token()
        self.client.post(self.confirm_url, {"uid": self.user.id, "token": token, "new_password": "BrandNewPass456!"})
        response = self.client.post(self.confirm_url, {"uid": self.user.id, "token": token, "new_password": "AnotherPass789!"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_token_is_rejected(self):
        self.client.post(self.request_url, {"email": "test@example.com"})
        response = self.client.post(self.confirm_url, {
            "uid": self.user.id, "token": "not-the-real-token", "new_password": "BrandNewPass456!",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass123!"))

    def test_unknown_email_gets_generic_response_not_an_error(self):
        response = self.client.post(self.request_url, {"email": "nobody@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EmailOtpModelTests(APITestCase):
    """Direct unit coverage of apps.users.services.issue_otp/verify_otp, beneath the API layer."""

    def setUp(self):
        self.user = User.objects.create_user(email="test@example.com", password="StrongPass123!", full_name="Test")

    def test_issuing_a_new_otp_invalidates_the_previous_unused_one(self):
        first = services.issue_otp(self.user, OTPPurpose.LOGIN)
        services.issue_otp(self.user, OTPPurpose.LOGIN)
        self.assertFalse(services.verify_otp(self.user, OTPPurpose.LOGIN, first))

    def test_expired_otp_is_rejected(self):
        code = services.issue_otp(self.user, OTPPurpose.LOGIN)
        EmailOTP.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertFalse(services.verify_otp(self.user, OTPPurpose.LOGIN, code))
