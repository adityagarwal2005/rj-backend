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

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == Role.ADMIN
