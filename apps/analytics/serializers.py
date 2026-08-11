from rest_framework import serializers

from apps.analytics.models import PageView


class PageViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageView
        fields = ["path", "referrer", "visitor_id"]
