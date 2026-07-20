from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.core.response import api_error, api_success
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """GET /api/notifications/ - the authenticated user's notifications."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkNotificationReadView(APIView):
    """PATCH /api/notifications/{id}/read/ - mark a single notification as read."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        try:
            notification = Notification.objects.get(id=id, user=request.user)
        except Notification.DoesNotExist:
            return api_error("Notification not found.", status=status.HTTP_404_NOT_FOUND)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return api_success(NotificationSerializer(notification).data, message="Notification marked as read.")
