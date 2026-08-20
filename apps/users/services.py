"""
Business logic for the users app. Views stay thin: validate the request via
a serializer, delegate to a service function, return the response.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.notifications import services as notification_services
from apps.users.models import EmailOTP, OTPPurpose, User
from apps.users.serializers import UserSerializer

OTP_CODE_LENGTH = 6
OTP_TTL_MINUTES = 10
PASSWORD_RESET_TTL_MINUTES = 30


def register_user(validated_data: dict) -> User:
    """
    New accounts start inactive - they can't log in (Django's own auth
    backend already refuses inactive users) until they verify the OTP
    just emailed to them. See VerifyEmailView.
    """
    password = validated_data.pop("password")
    referral_code = validated_data.pop("referral_code", "").strip().upper()
    validated_data["email"] = validated_data["email"].lower().strip()
    user = User(**validated_data, is_active=False)
    user.set_password(password)
    if referral_code:
        user.referred_by = User.objects.filter(referral_code=referral_code).first()
    user.save()
    return user


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_CODE_LENGTH):0{OTP_CODE_LENGTH}d}"


def issue_otp(user: User, purpose: str) -> str:
    """
    Invalidates any previous unused OTP of the same purpose, creates a
    fresh one, and returns the plaintext (signup/login: a 6-digit code the
    user types in; password reset: a long token embedded in an emailed
    link instead - same storage/verification either way).
    """
    EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    ttl_minutes = PASSWORD_RESET_TTL_MINUTES if purpose == OTPPurpose.PASSWORD_RESET else OTP_TTL_MINUTES
    plaintext = secrets.token_urlsafe(32) if purpose == OTPPurpose.PASSWORD_RESET else _generate_code()
    EmailOTP.objects.create(
        user=user, purpose=purpose, code_hash=make_password(plaintext),
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
    )
    return plaintext


def verify_otp(user: User, purpose: str, code: str) -> bool:
    """Checks `code` against the user's most recent unused OTP of this purpose. Consumes it (marks used) on success."""
    otp = EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).order_by("-created_at").first()
    if otp is None or not otp.is_valid():
        return False
    if not check_password(code, otp.code_hash):
        otp.failed_attempts += 1
        otp.save(update_fields=["failed_attempts"])
        return False
    otp.is_used = True
    otp.save(update_fields=["is_used"])
    return True


def send_signup_otp(user: User) -> None:
    code = issue_otp(user, OTPPurpose.SIGNUP)
    notification_services.send_otp_email(user, code, purpose=OTPPurpose.SIGNUP)


def send_login_otp(user: User) -> None:
    code = issue_otp(user, OTPPurpose.LOGIN)
    notification_services.send_otp_email(user, code, purpose=OTPPurpose.LOGIN)


def send_password_reset_email(user: User) -> None:
    token = issue_otp(user, OTPPurpose.PASSWORD_RESET)
    notification_services.send_password_reset_email(user, token)


def issue_tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["full_name"] = user.full_name
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": UserSerializer(user).data,
    }


def blacklist_refresh_token(refresh_token: str) -> None:
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except TokenError as exc:
        raise ValueError("Invalid or already blacklisted refresh token.") from exc
