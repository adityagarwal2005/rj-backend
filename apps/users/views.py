from decimal import Decimal

from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.response import api_error, api_success
from apps.users import services
from apps.users.models import OTPPurpose, ReferralCredit, User
from apps.users.serializers import (
    LoginSerializer,
    LogoutSerializer,
    OtpLoginRequestSerializer,
    OtpLoginVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ReferralCreditSerializer,
    RegisterSerializer,
    ResendOtpSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)


class RegisterView(APIView):
    """POST /api/auth/register - create an (inactive) account and email a verification code."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(serializer.validated_data)
        services.send_signup_otp(user)
        return api_success(
            {"email": user.email},
            message="Account created! Check your email for a verification code.",
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email - consume the signup OTP, activate the account, and log the user in."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None or not services.verify_otp(user, OTPPurpose.SIGNUP, serializer.validated_data["code"]):
            return api_error("That code is invalid or has expired.", status=status.HTTP_400_BAD_REQUEST)
        user.is_active = True
        user.save(update_fields=["is_active"])
        tokens = services.issue_tokens_for_user(user)
        return api_success(tokens, message="Email verified! You're all set.")


class ResendOtpView(APIView):
    """POST /api/auth/resend-otp - re-send the signup verification code for a not-yet-verified account."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = ResendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=False).first()
        if user is not None:
            services.send_signup_otp(user)
        # Same response either way - don't reveal whether that email is registered/already verified.
        return api_success(message="If that account needs verifying, a new code has been sent.")


class OtpLoginRequestView(APIView):
    """POST /api/auth/otp-login/request - email a one-time login code, as an alternative to a password."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = OtpLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None:
            services.send_login_otp(user)
        return api_success(message="If that account exists, a login code has been sent.")


class OtpLoginVerifyView(APIView):
    """POST /api/auth/otp-login/verify - exchange a valid login code for a token pair."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = OtpLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is None or not services.verify_otp(user, OTPPurpose.LOGIN, serializer.validated_data["code"]):
            return api_error("That code is invalid or has expired.", status=status.HTTP_400_BAD_REQUEST)
        tokens = services.issue_tokens_for_user(user)
        return api_success(tokens, message="Login successful.")


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/request - email a reset link if the account exists."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None:
            services.send_password_reset_email(user)
        return api_success(message="If that account exists, a reset link has been sent.")


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm - the link target: set a new password given a valid token."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(pk=serializer.validated_data["uid"], is_active=True).first()
        if user is None or not services.verify_otp(
            user, OTPPurpose.PASSWORD_RESET, serializer.validated_data["token"]
        ):
            return api_error("That reset link is invalid or has expired.", status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return api_success(message="Password reset! You can now log in with your new password.")


class LoginView(TokenObtainPairView):
    """POST /api/auth/login - exchange email/password for an access+refresh token pair."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (ValidationError, AuthenticationFailed):
            # simplejwt's TokenObtainSerializer.validate() raises AuthenticationFailed
            # (not ValidationError) when authenticate() fails - which it always does
            # for an inactive user, correct password or not - so this has to be
            # caught here too, or the check below for "wrong-but-unverified" never runs.
            email = str(request.data.get("email", "")).strip().lower()
            password = request.data.get("password", "")
            user = User.objects.filter(email=email, is_active=False).first()
            if user is not None and user.check_password(password):
                return api_error(
                    "Please verify your email before logging in.",
                    errors={"code": "email_not_verified", "email": email},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return api_error("Invalid email or password.", status=status.HTTP_401_UNAUTHORIZED)
        return api_success(serializer.validated_data, message="Login successful.")


class RefreshTokenView(TokenRefreshView):
    """POST /api/auth/refresh - exchange a refresh token for a new access token."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (ValidationError, TokenError):
            return api_error("Refresh token is invalid or expired.", status=status.HTTP_401_UNAUTHORIZED)
        return api_success(serializer.validated_data, message="Token refreshed successfully.")


class LogoutView(APIView):
    """POST /api/auth/logout - blacklist the given refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.blacklist_refresh_token(serializer.validated_data["refresh"])
        except ValueError as exc:
            return api_error(str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(message="Logged out successfully.")


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PUT/PATCH /api/auth/profile - the authenticated user's own profile."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return api_success(self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Profile updated successfully.")


class ReferralSummaryView(APIView):
    """GET /api/auth/referrals/ - the authenticated user's referral code, stats, and earned credits."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        credits = ReferralCredit.objects.filter(user=user)
        available_credit = sum((c.amount for c in credits if not c.is_used), Decimal("0"))
        return api_success({
            "referral_code": user.referral_code,
            "referred_count": User.objects.filter(referred_by=user).count(),
            "successful_referrals": User.objects.filter(referred_by=user, referral_reward_granted=True).count(),
            "available_credit": available_credit,
            "credits": ReferralCreditSerializer(credits, many=True).data,
        })
