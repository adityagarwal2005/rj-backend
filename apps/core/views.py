from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.response import api_success


class HealthCheckView(APIView):
    """
    GET /api/health/ - trivial liveness check for external uptime monitors
    (e.g. UptimeRobot) to ping and keep the free-tier Render instance from
    spinning down. No auth, does a real (if trivial) DB round trip so a
    ping actually exercises the same warm-up path as a real request.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return api_success({"status": "ok"})
