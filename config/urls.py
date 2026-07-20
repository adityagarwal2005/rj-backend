"""
Root URL configuration.

Every app owns its own urls.py; this file only mounts them under a stable
/api/ prefix so the React frontend has one predictable base path per
resource. Changing an app's internal view structure never needs to touch
this file.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
]
