import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

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
