from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationType(models.TextChoices):
    ORDER_UPDATE = "order_update", "Order Update"
    PROMOTION = "promotion", "Promotion"
    SYSTEM = "system", "System"


class Notification(TimeStampedModel):
    """In-app notification record. Email delivery is a side effect, tracked separately below."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=20, choices=NotificationType.choices, default=NotificationType.SYSTEM)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.title} -> {self.user.email}"
