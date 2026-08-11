from django.db import models


class PageView(models.Model):
    """
    One row per frontend page load, logged by the SPA itself (see
    apps.analytics.views.PageViewCreateView) since Django never renders
    these pages directly. No IP/user-agent is stored - path, referrer, and
    a client-generated visitor_id (localStorage UUID, not tied to identity)
    are enough for "how many people, which pages" without collecting PII.
    """

    path = models.CharField(max_length=255, db_index=True)
    referrer = models.CharField(max_length=255, blank=True)
    visitor_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.path} @ {self.created_at:%Y-%m-%d %H:%M}"
