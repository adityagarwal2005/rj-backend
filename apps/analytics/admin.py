from django.contrib import admin

from apps.analytics.models import PageView


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ["path", "referrer", "visitor_id", "created_at"]
    list_filter = ["path"]
    search_fields = ["path", "referrer", "visitor_id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
