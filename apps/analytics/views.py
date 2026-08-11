from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.analytics.models import PageView
from apps.analytics.serializers import PageViewSerializer
from apps.core.response import api_success


class PageViewCreateView(generics.CreateAPIView):
    """
    Public, unauthenticated, write-only sink for frontend page loads.
    Scoped-throttled per IP so it can't be abused to fill the table.
    """

    queryset = PageView.objects.all()
    serializer_class = PageViewSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "pageview"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(message="Recorded", status=201)
