from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("<int:id>/read/", views.MarkNotificationReadView.as_view(), name="notification-mark-read"),
]
