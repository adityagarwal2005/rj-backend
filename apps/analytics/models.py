from django.db import models


class PageView(models.Model):
    """
    One row per frontend page load, logged by the SPA itself (see
    apps.analytics.views.PageViewCreateView) since Django never renders
    these pages directly.

    Still no IP or user-agent. The city/state/country below are resolved at
    the edge (see apps.analytics.geo) and arrive already coarsened, so the
    dashboard can answer "how many people from Jaipur yesterday" without
    this table ever holding an address that identifies anyone.
    """

    path = models.CharField(max_length=255, db_index=True)
    referrer = models.CharField(max_length=255, blank=True)
    visitor_id = models.CharField(max_length=36, db_index=True)

    # Blank whenever the request didn't pass through an edge that resolves
    # location - local development, or a direct hit on the Cloud Run URL.
    city = models.CharField(max_length=100, blank=True, db_index=True)
    region = models.CharField(max_length=100, blank=True, db_index=True)
    country = models.CharField(max_length=2, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The dashboard's two main queries: "last N days by day" and
            # "last N days grouped by city/state".
            models.Index(fields=["created_at", "city"]),
            models.Index(fields=["created_at", "region"]),
        ]

    def __str__(self):
        where = self.city or self.region or self.country or "unknown"
        return f"{self.path} from {where} @ {self.created_at:%Y-%m-%d %H:%M}"
