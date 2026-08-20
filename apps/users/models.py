import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.users.managers import UserManager


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    ADMIN = "admin", "Admin"


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Custom user model, keyed by email instead of username.

    Kept deliberately small - shipping/billing details live on
    apps.orders.Address, not here, so the auth model never has to change
    shape when checkout requirements evolve.
    """

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # --- Referral program (see apps.orders.referrals for the discount/reward rules) ---
    referral_code = models.CharField(max_length=12, unique=True, blank=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals_made"
    )
    # Set once the referrer's reward for THIS user's referral has been granted,
    # so it can never be granted twice even if signals fire more than once.
    referral_reward_granted = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._generate_referral_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_referral_code() -> str:
        while True:
            code = secrets.token_hex(4).upper()
            if not User.objects.filter(referral_code=code).exists():
                return code

    @property
    def is_admin(self):
        return self.role == Role.ADMIN


class ReferralCredit(TimeStampedModel):
    """
    A flat-amount discount earned by referring a friend, redeemable on the
    referrer's next order (see apps.orders.referrals.grant_referrer_reward_if_eligible,
    which creates these, and create_order_from_cart, which spends them).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_credits")
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    is_used = models.BooleanField(default=False)
    used_on_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "used" if self.is_used else "available"
        return f"₹{self.amount} credit for {self.user.email} ({status})"


class OTPPurpose(models.TextChoices):
    SIGNUP = "signup", "Signup Verification"
    LOGIN = "login", "Login"
    PASSWORD_RESET = "password_reset", "Password Reset"


# Failed guesses allowed against one OTP before it's locked out - independent
# of and in addition to request-rate throttling on the verify endpoints
# themselves (see the "otp" throttle scope), since a 6-digit code is only
# ~1M possibilities and needs its own hard ceiling regardless of how fast
# someone can fire requests.
MAX_OTP_ATTEMPTS = 5


class EmailOTP(TimeStampedModel):
    """
    A short-lived, single-use secret emailed to prove control of an email
    address - a 6-digit code for signup verification / login, or a long
    random token embedded in a link for password reset (see
    apps.users.services.issue_otp, which decides which). Hashed at rest
    (same as a password) so a database leak doesn't hand out usable codes.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    failed_attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose", "is_used"])]

    def __str__(self):
        return f"{self.get_purpose_display()} OTP for {self.user.email}"

    def is_valid(self) -> bool:
        return not self.is_used and self.failed_attempts < MAX_OTP_ATTEMPTS and timezone.now() < self.expires_at
